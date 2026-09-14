"""Validated manifest for declarative and containerised extensions."""

from __future__ import annotations

from enum import StrEnum
import re

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

_EXTENSION_ID = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)+$")
_IMAGE = re.compile(r"^[a-z0-9][a-z0-9._/-]*(?::[A-Za-z0-9._-]+)?(?:@sha256:[0-9a-f]{64})?$")


class ExtensionType(StrEnum):
    """Supported extension implementation types."""

    MODBUS_DEVICE_PACK = "modbus_device_pack"
    AUTOMATION_PACK = "automation_pack"
    DASHBOARD_PACK = "dashboard_pack"
    INTEGRATION = "integration"
    APP = "app"


class Capabilities(BaseModel):
    """Capabilities requested by an extension and explicitly approved by a user."""

    network: bool = False
    mqtt: bool = False
    serial_devices: list[str] = Field(default_factory=list)
    usb: bool = False
    gpio: bool = False
    host_network: bool = False

    @field_validator("serial_devices")
    @classmethod
    def valid_serial_devices(cls, values: list[str]) -> list[str]:
        if any(not value.startswith("/dev/") or ".." in value for value in values):
            raise ValueError("serial devices must be absolute paths below /dev")
        return values


class ContainerRuntime(BaseModel):
    """Container configuration for a Linux app extension."""

    image: str
    command: list[str] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)
    ports: list[int] = Field(default_factory=list)
    healthcheck_url: HttpUrl | None = None

    @field_validator("image")
    @classmethod
    def pinned_image(cls, value: str) -> str:
        if not _IMAGE.fullmatch(value) or ":latest" in value:
            raise ValueError("container image must be valid and may not use the latest tag")
        return value

    @field_validator("ports")
    @classmethod
    def valid_ports(cls, values: list[int]) -> list[int]:
        if len(set(values)) != len(values) or any(port < 1 or port > 65535 for port in values):
            raise ValueError("ports must be unique values between 1 and 65535")
        return values


class ExtensionManifest(BaseModel):
    """Top-level extension package contract."""

    schema_version: int = 2
    id: str
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
    type: ExtensionType
    summary: str = Field(default="", max_length=300)
    documentation_url: HttpUrl | None = None
    permissions: Capabilities = Field(default_factory=Capabilities)
    runtime: ContainerRuntime | None = None

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        if not _EXTENSION_ID.fullmatch(value):
            raise ValueError("extension ID must be lowercase and namespaced")
        return value

    @model_validator(mode="after")
    def validates_runtime(self) -> "ExtensionManifest":
        if self.type is ExtensionType.APP and self.runtime is None:
            raise ValueError("app extensions require a container runtime")
        if self.type is not ExtensionType.APP and self.runtime is not None:
            raise ValueError("only app extensions may declare a container runtime")
        if self.permissions.host_network and not self.permissions.network:
            raise ValueError("host network requires network permission")
        return self
