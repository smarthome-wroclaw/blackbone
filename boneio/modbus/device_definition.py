"""Pydantic validation for Modbus device definition JSON files."""
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")

class RegisterFilter(BaseModel):
    model_config = _STRICT
    multiply: float | None = None
    offset: float | None = None
    round: int | None = None
    firmware_version: int | None = None
    encode_temperature: int | None = None

class RegisterDef(BaseModel):
    model_config = _STRICT
    name: str
    address: int = Field(ge=0)
    unit_of_measurement: str | None = None
    state_class: str | None = None
    device_class: str | None = None
    value_type: str
    entity_type: str | None = None
    entity_category: str | None = None
    filters: list[RegisterFilter] | None = None
    write_filters: list[RegisterFilter] | None = None
    write_address: int | None = None
    payload_on: Any | None = None
    payload_off: Any | None = None
    x_mapping: dict[str, str] | None = None
    step: float | None = None
    ha_filter: str | None = None

class RegisterBlock(BaseModel):
    model_config = _STRICT
    base: int = Field(ge=0)
    length: int = Field(ge=1)
    register_type: Literal["input", "holding", "coil"] = "input"
    update_every_n: int | None = Field(default=None, ge=1)
    registers: list[RegisterDef] = Field(min_length=1)

class SetBaudrate(BaseModel):
    model_config = _STRICT
    address: int = Field(ge=0)
    possible_baudrates: dict[str, int]

class SetBase(BaseModel):
    model_config = _STRICT
    set_address_address: int | None = None
    set_baudrate: SetBaudrate | None = None

class AdditionalEntity(BaseModel):
    model_config = _STRICT
    name: str
    source: str | list[str]
    entity_type: str | None = None
    entity_category: str | None = None
    unit_of_measurement: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    x_mapping: dict[str, str] | None = None
    payload_on: Any | None = None
    payload_off: Any | None = None
    formula: str | None = None
    operation: str | None = None
    config_keys: list[str] | None = None

class ModbusDeviceDefinition(BaseModel):
    model_config = _STRICT
    model: str = Field(min_length=1)
    manufacturer: str | None = None
    description: str | None = None
    category: str | None = None
    default_address: int | None = Field(default=None, ge=1, le=247)
    default_update_interval: str | None = None
    set_base: SetBase | None = None
    registers_base: list[RegisterBlock] = Field(min_length=1)
    additional_entities: list[AdditionalEntity] | None = None

def validate_definition(data: dict) -> ModbusDeviceDefinition:
    return ModbusDeviceDefinition.model_validate(data)
