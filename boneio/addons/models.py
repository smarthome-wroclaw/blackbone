"""Strict persistent and wire models for add-ons."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

ADDON_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)+$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
REPOSITORY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")
UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
STRICT_MODEL = ConfigDict(extra="forbid")


def validate_addon_id(value: str) -> str:
    if len(value) > 128 or not ADDON_ID_PATTERN.fullmatch(value):
        raise ValueError("must be a namespaced lowercase identifier")
    return value


def validate_release_version(value: str) -> str:
    try:
        parsed = Version(value)
    except InvalidVersion as exc:
        raise ValueError("must be a valid release version") from exc
    if (
        parsed.epoch
        or parsed.local is not None
        or parsed.dev is not None
        or len(parsed.release) != 3
        or str(parsed) != value
    ):
        raise ValueError("must be a three-part public release version")
    return value


def validate_sha256(value: str) -> str:
    if not HASH_PATTERN.fullmatch(value):
        raise ValueError("must be 64 lowercase hexadecimal characters")
    return value


def validate_repository_id(value: str) -> str:
    if not REPOSITORY_ID_PATTERN.fullmatch(value):
        raise ValueError("must be a lowercase repository identifier")
    return value


def validate_uuid(value: str) -> str:
    if not UUID_PATTERN.fullmatch(value):
        raise ValueError("must be a lowercase UUID")
    return value


def validate_logical_path(value: str) -> str:
    if not value or len(value) > 240 or "\\" in value or CONTROL_PATTERN.search(value):
        raise ValueError("contains invalid characters")
    if value.startswith("/") or "//" in value or value.endswith("/"):
        raise ValueError("must be a normalized relative path")
    path = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("must not contain empty, current, or parent segments")
    if len(path.parts) != 2 or path.parts[0] != "modbus_devices" or path.suffix != ".json":
        raise ValueError("must identify a JSON file directly below modbus_devices/")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", path.stem):
        raise ValueError("device filename must be a lowercase Modbus model key")
    return value


AddonId = Annotated[str, Field(min_length=3, max_length=128)]
Sha256 = Annotated[str, Field(min_length=64, max_length=64)]


class RepositoryTrust(StrEnum):
    OFFICIAL = "official"
    CUSTOM = "custom"


class Repository(BaseModel):
    model_config = STRICT_MODEL

    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    url: HttpUrl
    trust: RepositoryTrust
    enabled: bool = True

    _validate_id = field_validator("id")(validate_repository_id)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https" or value.username or value.password or value.fragment:
            raise ValueError("repository URL must be HTTPS without credentials or a fragment")
        return value


class RepositoryState(BaseModel):
    model_config = STRICT_MODEL

    schema_version: Literal[1] = 1
    repositories: list[Repository] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def unique_repositories(self) -> Self:
        ids = [item.id for item in self.repositories]
        urls = [str(item.url) for item in self.repositories]
        if len(ids) != len(set(ids)) or len(urls) != len(set(urls)):
            raise ValueError("repository IDs and URLs must be unique")
        return self


class ManifestFile(BaseModel):
    model_config = STRICT_MODEL

    path: str
    sha256: Sha256

    _validate_path = field_validator("path")(validate_logical_path)
    _validate_hash = field_validator("sha256")(validate_sha256)


class BlackBoneCompatibility(BaseModel):
    model_config = STRICT_MODEL

    version: str = Field(min_length=1, max_length=200)

    @field_validator("version")
    @classmethod
    def valid_specifier(cls, value: str) -> str:
        try:
            SpecifierSet(value)
        except InvalidSpecifier as exc:
            raise ValueError("must be a valid PEP 440 version specifier") from exc
        return value


class Author(BaseModel):
    model_config = STRICT_MODEL

    name: str = Field(min_length=1, max_length=120)


class AddonManifest(BaseModel):
    model_config = STRICT_MODEL

    schema_version: Literal[1]
    id: AddonId
    name: str = Field(min_length=1, max_length=120)
    version: str
    type: Literal["modbus_device_pack"]
    blackbone: BlackBoneCompatibility
    author: Author
    license: str = Field(min_length=1, max_length=80)
    files: list[ManifestFile] = Field(min_length=1, max_length=64)

    _validate_id = field_validator("id")(validate_addon_id)
    _validate_version = field_validator("version")(validate_release_version)

    @model_validator(mode="after")
    def unique_paths(self) -> Self:
        paths = [item.path for item in self.files]
        folded = [item.casefold() for item in paths]
        if len(paths) != len(set(paths)):
            raise ValueError("manifest contains duplicate logical paths")
        if len(folded) != len(set(folded)):
            raise ValueError("manifest contains case-folded path collisions")
        return self


class IndexAddon(BaseModel):
    model_config = STRICT_MODEL

    id: AddonId
    name: str = Field(min_length=1, max_length=120)
    version: str
    type: Literal["modbus_device_pack"]
    blackbone: BlackBoneCompatibility
    manifest_url: str = Field(min_length=1, max_length=2048)
    manifest_sha256: Sha256

    _validate_id = field_validator("id")(validate_addon_id)
    _validate_version = field_validator("version")(validate_release_version)
    _validate_hash = field_validator("manifest_sha256")(validate_sha256)


class RepositoryIndex(BaseModel):
    model_config = STRICT_MODEL

    schema_version: Literal[1]
    addons: list[IndexAddon] = Field(default_factory=list, max_length=2000)

    @model_validator(mode="after")
    def unique_releases(self) -> Self:
        keys = [(item.id, item.version) for item in self.addons]
        if len(keys) != len(set(keys)):
            raise ValueError("repository contains a duplicate add-on version")
        return self


class InstalledAddon(BaseModel):
    model_config = STRICT_MODEL

    version: str
    repository_id: str = Field(min_length=1, max_length=128)
    manifest_sha256: Sha256
    enabled: bool = True
    installed_at: datetime
    files: list[str] = Field(min_length=1, max_length=64)
    last_operation_id: str

    _validate_version = field_validator("version")(validate_release_version)
    _validate_hash = field_validator("manifest_sha256")(validate_sha256)
    _validate_files = field_validator("files")(lambda values: [validate_logical_path(value) for value in values])
    _validate_repository = field_validator("repository_id")(validate_repository_id)
    _validate_operation = field_validator("last_operation_id")(validate_uuid)


class InstalledState(BaseModel):
    model_config = STRICT_MODEL

    schema_version: Literal[1] = 1
    installed: dict[str, InstalledAddon] = Field(default_factory=dict)

    @field_validator("installed")
    @classmethod
    def valid_keys(cls, value: dict[str, InstalledAddon]) -> dict[str, InstalledAddon]:
        for key in value:
            validate_addon_id(key)
        return value


class OperationType(StrEnum):
    INSTALL = "install"
    UPDATE = "update"
    ENABLE = "enable"
    DISABLE = "disable"
    REMOVE = "remove"
    ROLLBACK = "rollback"


class OperationStage(StrEnum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    VALIDATING = "validating"
    APPLYING = "applying"
    RELOADING = "reloading"
    ROLLING_BACK = "rolling_back"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class ValidationIssue(BaseModel):
    model_config = STRICT_MODEL

    code: str
    message: str
    file: str | None = None
    model: str | None = None


class OperationRecord(BaseModel):
    model_config = STRICT_MODEL

    id: str
    type: OperationType
    addon_id: AddonId
    version: str | None = None
    repository_id: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    stage: OperationStage = OperationStage.PENDING
    message: str = "Operation queued."
    validation_errors: list[ValidationIssue] = Field(default_factory=list)
    snapshot_path: str | None = None
    reload_required: bool = False
    restart_required: bool = False

    _validate_id = field_validator("addon_id")(validate_addon_id)
    _validate_operation_id = field_validator("id")(validate_uuid)

    @field_validator("version")
    @classmethod
    def validate_optional_version(cls, value: str | None) -> str | None:
        return validate_release_version(value) if value is not None else None

    @field_validator("repository_id")
    @classmethod
    def validate_optional_repository(cls, value: str | None) -> str | None:
        return validate_repository_id(value) if value is not None else None


class PreviewRequest(BaseModel):
    model_config = STRICT_MODEL

    repository_id: str
    version: str
    action: Literal["install", "update", "downgrade"] = "install"

    _validate_version = field_validator("version")(validate_release_version)


class ConfirmRequest(BaseModel):
    model_config = STRICT_MODEL

    confirmation_token: str = Field(min_length=32, max_length=8192)


class RepositoryCreateRequest(BaseModel):
    model_config = STRICT_MODEL

    name: str = Field(min_length=1, max_length=120)
    url: HttpUrl


class RollbackRequest(BaseModel):
    model_config = STRICT_MODEL

    snapshot_id: str = Field(min_length=1, max_length=128)


class RemoveRequest(BaseModel):
    model_config = STRICT_MODEL

    confirmation: str = Field(min_length=1, max_length=128)
