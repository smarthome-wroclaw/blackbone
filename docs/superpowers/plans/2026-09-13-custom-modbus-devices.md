# Własne urządzenia Modbus — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Umożliwić dodawanie własnych definicji urządzeń Modbus z poziomu WebUI (kreator + import pliku JSON), tak by przetrwały aktualizację pakietu i były od razu wybieralne w konfiguracji.

**Architecture:** Definicje użytkownika leżą w `<katalog_config.yaml>/modbus_devices/*.json` w tym samym formacie co wbudowane. Nowy moduł `boneio/modbus/device_registry.py` jest jedynym miejscem znającym lokalizacje definicji; wszystkie dzisiejsze punkty skanujące katalog pakietu przechodzą na niego. Zapis przez REST waliduje definicję modelem pydantic i przebudowuje działające koordynatory tego modelu bez restartu.

**Tech Stack:** Python 3.13, FastAPI, pydantic v2, cerberus, pytest (`asyncio_mode = "auto"`), React + TypeScript, vitest, DaisyUI/Tailwind.

**Spec:** `docs/superpowers/specs/2026-09-10-custom-modbus-devices-design.md`

## Global Constraints

- Klucz modelu: wzorzec `^[a-z0-9][a-z0-9_-]{1,63}$` — stosowany identycznie w backendzie i frontendzie.
- Katalog własnych definicji: `<katalog config.yaml>/modbus_devices/`, płaski, jeden plik `<klucz>.json`.
- Model wbudowany ma zawsze pierwszeństwo przy odczycie; zapis pod kluczem wbudowanego jest odrzucany.
- Domyślny `register_type` dla bloku bez tego pola: `"input"` (zgodnie z `boneio/modbus/coordinator.py:626`).
- Format `config.yaml` nie zmienia się w żadnym zadaniu.
- Instalacja bez katalogu własnych musi zachowywać się identycznie jak dziś (ścieżka `configure(None)`).
- Commity konwencjonalne z zakresem `modbus`, np. `feat(modbus): ...`, `test(modbus): ...`.
- Testy uruchamiane z katalogu repo przez `.venv/bin/pytest`; frontendowe przez `npm run test` w `frontend/`.

---

### Task 1: Rejestr modeli

Jedyny moduł znający lokalizacje definicji. Wszystkie dalsze zadania backendowe z niego korzystają.

**Files:**
- Create: `boneio/modbus/device_registry.py`
- Test: `tests/unit/modbus/test_device_registry.py`

**Interfaces:**
- Consumes: nic (pierwsze zadanie)
- Produces:
  - `ModelRef(key: str, path: str, source: str)` — dataclass, `source` to `"builtin"` albo `"custom"`
  - `ModelNotFoundError(Exception)`
  - `configure(custom_dir: str | None) -> None`
  - `get_custom_dir() -> str | None`
  - `is_valid_key(key: str) -> bool`
  - `list_models() -> list[ModelRef]` — posortowane po `key`
  - `get_model_ref(key: str) -> ModelRef`
  - `load_model(key: str) -> dict`
  - `custom_path_for(key: str) -> str`
  - `invalidate() -> None`

- [ ] **Step 1: Write the failing test**

Utwórz `tests/unit/modbus/test_device_registry.py`:

```python
"""Tests for the Modbus device registry (builtin + user-provided models)."""

import json
import os

import pytest

from boneio.modbus import device_registry


@pytest.fixture(autouse=True)
def _reset_registry():
    """Every test starts from a registry with no custom directory."""
    device_registry.configure(None)
    yield
    device_registry.configure(None)


def _write_model(directory: str, key: str, model_name: str) -> str:
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{key}.json")
    with open(path, "w") as fh:
        json.dump(
            {
                "model": model_name,
                "registers_base": [
                    {
                        "base": 0,
                        "length": 1,
                        "register_type": "input",
                        "registers": [
                            {
                                "name": "Temperature",
                                "address": 0,
                                "unit_of_measurement": "°C",
                                "state_class": "measurement",
                                "value_type": "S_WORD",
                            }
                        ],
                    }
                ],
            },
            fh,
        )
    return path


def test_lists_builtin_models_without_custom_dir():
    keys = {ref.key for ref in device_registry.list_models()}
    assert "sdm120" in keys
    assert "sht30" in keys
    assert all(ref.source == "builtin" for ref in device_registry.list_models())


def test_lists_custom_models_from_configured_dir(tmp_path):
    custom = str(tmp_path / "modbus_devices")
    _write_model(custom, "mymeter", "My Meter")
    device_registry.configure(custom)

    refs = {ref.key: ref for ref in device_registry.list_models()}
    assert refs["mymeter"].source == "custom"
    assert refs["sdm120"].source == "builtin"


def test_builtin_wins_over_custom_with_same_key(tmp_path, caplog):
    custom = str(tmp_path / "modbus_devices")
    _write_model(custom, "sdm120", "Hijacked")
    device_registry.configure(custom)

    ref = device_registry.get_model_ref("sdm120")
    assert ref.source == "builtin"
    assert device_registry.load_model("sdm120")["model"] != "Hijacked"
    assert any("sdm120" in record.message for record in caplog.records)


def test_load_model_returns_parsed_custom_definition(tmp_path):
    custom = str(tmp_path / "modbus_devices")
    _write_model(custom, "mymeter", "My Meter")
    device_registry.configure(custom)

    assert device_registry.load_model("mymeter")["model"] == "My Meter"


def test_unknown_key_raises():
    with pytest.raises(device_registry.ModelNotFoundError):
        device_registry.load_model("no-such-model")


@pytest.mark.parametrize(
    "key",
    ["../escape", "UPPER", "with space", "", "a", "x" * 65, "-leading"],
)
def test_invalid_keys_rejected(key):
    assert device_registry.is_valid_key(key) is False


@pytest.mark.parametrize("key", ["sdm120", "my-meter", "my_meter_2", "a1"])
def test_valid_keys_accepted(key):
    assert device_registry.is_valid_key(key) is True


def test_custom_path_for_rejects_invalid_key(tmp_path):
    device_registry.configure(str(tmp_path / "modbus_devices"))
    with pytest.raises(ValueError):
        device_registry.custom_path_for("../escape")


def test_new_file_is_picked_up_without_restart(tmp_path):
    custom = str(tmp_path / "modbus_devices")
    os.makedirs(custom)
    device_registry.configure(custom)
    assert "later" not in {ref.key for ref in device_registry.list_models()}

    _write_model(custom, "later", "Added Later")
    device_registry.invalidate()

    assert "later" in {ref.key for ref in device_registry.list_models()}


def test_missing_custom_dir_is_not_an_error(tmp_path):
    device_registry.configure(str(tmp_path / "does-not-exist"))
    keys = {ref.key for ref in device_registry.list_models()}
    assert "sdm120" in keys
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/modbus/test_device_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'boneio.modbus.device_registry'`

- [ ] **Step 3: Write minimal implementation**

Utwórz `boneio/modbus/device_registry.py`:

```python
"""Single source of truth for Modbus device definitions.

Definitions ship with the package in ``boneio/modbus/devices/**`` and may be
extended by the user with JSON files placed in a directory next to
``config.yaml``. Built-in definitions always win on key collision so a file
dropped in by hand cannot silently shadow a shipped model.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

BUILTIN_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "devices"))
MODEL_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")


class ModelNotFoundError(Exception):
    """Raised when a model key matches no definition."""


@dataclass(frozen=True)
class ModelRef:
    """Location and provenance of a single model definition."""

    key: str
    path: str
    source: str  # "builtin" | "custom"


_lock = threading.RLock()
_custom_dir: str | None = None
_builtin_index: dict[str, str] | None = None
_custom_index: dict[str, str] | None = None
_custom_stamp: tuple[float, int] | None = None


def is_valid_key(key: str) -> bool:
    """Return True when ``key`` is a safe model key."""
    return bool(MODEL_KEY_RE.match(key or ""))


def configure(custom_dir: str | None) -> None:
    """Point the registry at the user's definition directory (or nowhere)."""
    global _custom_dir, _custom_index, _custom_stamp
    with _lock:
        normalized = os.path.normpath(custom_dir) if custom_dir else None
        if normalized != _custom_dir:
            _LOGGER.debug("Modbus custom device directory set to %s", normalized)
        _custom_dir = normalized
        _custom_index = None
        _custom_stamp = None


def get_custom_dir() -> str | None:
    """Return the configured custom definition directory, if any."""
    return _custom_dir


def invalidate() -> None:
    """Drop the cached custom index (call after writing a definition)."""
    global _custom_index, _custom_stamp
    with _lock:
        _custom_index = None
        _custom_stamp = None


def custom_path_for(key: str) -> str:
    """Return the on-disk path a custom definition with ``key`` would take."""
    if not is_valid_key(key):
        raise ValueError(f"Invalid model key: {key!r}")
    if not _custom_dir:
        raise ValueError("Custom Modbus device directory is not configured")
    return os.path.join(_custom_dir, f"{key}.json")


def _scan(directory: str) -> dict[str, str]:
    index: dict[str, str] = {}
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fname in files:
            if fname.endswith(".json"):
                index.setdefault(fname[:-5], os.path.join(root, fname))
    return index


def _builtins() -> dict[str, str]:
    global _builtin_index
    with _lock:
        if _builtin_index is None:
            _builtin_index = _scan(BUILTIN_DIR) if os.path.isdir(BUILTIN_DIR) else {}
        return _builtin_index


def _customs() -> dict[str, str]:
    global _custom_index, _custom_stamp
    with _lock:
        if not _custom_dir or not os.path.isdir(_custom_dir):
            _custom_index = {}
            return _custom_index
        st = os.stat(_custom_dir)
        stamp = (st.st_mtime, st.st_size)
        if _custom_index is None or stamp != _custom_stamp:
            _custom_index = _scan(_custom_dir)
            _custom_stamp = stamp
        return _custom_index


def list_models() -> list[ModelRef]:
    """Return every known model, built-ins winning on key collision."""
    builtins = _builtins()
    customs = _customs()
    refs = [ModelRef(key=k, path=p, source="builtin") for k, p in builtins.items()]
    for key, path in customs.items():
        if key in builtins:
            _LOGGER.warning(
                "Custom Modbus definition %s shadows a built-in model and is ignored; "
                "rename it to use it",
                key,
            )
            continue
        refs.append(ModelRef(key=key, path=path, source="custom"))
    return sorted(refs, key=lambda ref: ref.key)


def get_model_ref(key: str) -> ModelRef:
    """Return the reference for ``key`` or raise ``ModelNotFoundError``."""
    for ref in list_models():
        if ref.key == key:
            return ref
    raise ModelNotFoundError(f"Modbus model '{key}' not found")


def load_model(key: str) -> dict:
    """Load and parse the definition for ``key``."""
    ref = get_model_ref(key)
    with open(ref.path) as fh:
        return json.load(fh)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/modbus/test_device_registry.py -v`
Expected: PASS (13 testów)

- [ ] **Step 5: Commit**

```bash
git add boneio/modbus/device_registry.py tests/unit/modbus/test_device_registry.py
git commit -m "feat(modbus): add device registry for builtin and user definitions"
```

---

### Task 2: Model definicji urządzenia (pydantic)

Walidacja plików definicji. Test parametryzowany po wbudowanych plikach jest kotwicą: gwarantuje, że model odwzorowuje realny format.

**Files:**
- Create: `boneio/modbus/device_definition.py`
- Test: `tests/unit/modbus/test_device_definition.py`

**Interfaces:**
- Consumes: `device_registry.BUILTIN_DIR` (tylko w teście)
- Produces:
  - `ModbusDeviceDefinition` — model pydantic całej definicji
  - `RegisterBlock`, `RegisterDef`, `AdditionalEntity`, `SetBase`, `SetBaudrate`
  - `validate_definition(data: dict) -> ModbusDeviceDefinition` — rzuca `pydantic.ValidationError`

- [ ] **Step 1: Write the failing test**

Utwórz `tests/unit/modbus/test_device_definition.py`:

```python
"""Tests for Modbus device definition validation."""

import json
import os

import pytest
from pydantic import ValidationError

from boneio.modbus.device_definition import validate_definition
from boneio.modbus.device_registry import BUILTIN_DIR


def _builtin_paths() -> list[str]:
    paths = []
    for root, dirs, files in os.walk(BUILTIN_DIR):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fname in sorted(files):
            if fname.endswith(".json"):
                paths.append(os.path.join(root, fname))
    return paths


BUILTIN_PATHS = _builtin_paths()


def test_builtin_paths_were_found():
    assert len(BUILTIN_PATHS) >= 27


@pytest.mark.parametrize("path", BUILTIN_PATHS, ids=lambda p: os.path.basename(p))
def test_every_builtin_definition_validates(path):
    """The definition model must describe the format we actually ship."""
    with open(path) as fh:
        data = json.load(fh)
    validate_definition(data)


def test_block_register_type_defaults_to_input():
    definition = validate_definition(
        {
            "model": "Minimal",
            "registers_base": [
                {
                    "base": 0,
                    "length": 1,
                    "registers": [
                        {
                            "name": "Temperature",
                            "address": 0,
                            "unit_of_measurement": "°C",
                            "state_class": "measurement",
                            "value_type": "S_WORD",
                        }
                    ],
                }
            ],
        }
    )
    assert definition.registers_base[0].register_type == "input"


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        validate_definition(
            {
                "model": "Typo",
                "manufacturerr": "Acme",
                "registers_base": [
                    {
                        "base": 0,
                        "length": 1,
                        "registers": [
                            {
                                "name": "T",
                                "address": 0,
                                "unit_of_measurement": "°C",
                                "state_class": "measurement",
                                "value_type": "S_WORD",
                            }
                        ],
                    }
                ],
            }
        )


def test_empty_registers_base_is_rejected():
    with pytest.raises(ValidationError):
        validate_definition({"model": "Empty", "registers_base": []})


def test_missing_model_is_rejected():
    with pytest.raises(ValidationError):
        validate_definition({"registers_base": []})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/modbus/test_device_definition.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'boneio.modbus.device_definition'`

- [ ] **Step 3: Write minimal implementation**

Utwórz `boneio/modbus/device_definition.py`. Zestaw pól odpowiada dokładnie temu, co występuje w 27 wbudowanych plikach — nic nie zgadujemy:

```python
"""Validation model for Modbus device definition files.

Covers every field present in the shipped definitions, including the ones the
WebUI creator does not edit (writable registers, derived entities), so an
imported community file validates and keeps working at runtime.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")


class RegisterFilter(BaseModel):
    """A single value transformation applied to a raw register reading."""

    model_config = _STRICT

    multiply: float | None = None
    offset: float | None = None
    round: int | None = None
    firmware_version: int | None = None  # shipped files use 0/1, not true/false


class RegisterDef(BaseModel):
    """One register exposed as an entity."""

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
    """A contiguous range of registers read in a single Modbus request."""

    model_config = _STRICT

    base: int = Field(ge=0)
    length: int = Field(ge=1)
    register_type: Literal["input", "holding"] = "input"
    update_every_n: int | None = Field(default=None, ge=1)
    registers: list[RegisterDef] = Field(min_length=1)


class SetBaudrate(BaseModel):
    """Register used to change the device baudrate."""

    model_config = _STRICT

    address: int = Field(ge=0)
    possible_baudrates: dict[str, int]


class SetBase(BaseModel):
    """Registers used to reconfigure address and baudrate."""

    model_config = _STRICT

    set_address_address: int | None = None
    set_baudrate: SetBaudrate | None = None


class AdditionalEntity(BaseModel):
    """Entity derived from one or more registers rather than read directly."""

    model_config = _STRICT

    name: str
    source: str
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
    """A complete Modbus device definition file."""

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
    """Validate a raw definition dict, raising ``ValidationError`` on problems."""
    return ModbusDeviceDefinition.model_validate(data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/modbus/test_device_definition.py -v`
Expected: PASS (wszystkie 27 wbudowanych plików + 5 testów jednostkowych)

Jeśli któryś wbudowany plik nie przejdzie — model definicji jest niepełny, **nie** plik. Dopisz brakujące pole do odpowiedniego modelu i uruchom ponownie.

- [ ] **Step 5: Commit**

```bash
git add boneio/modbus/device_definition.py tests/unit/modbus/test_device_definition.py
git commit -m "feat(modbus): add pydantic validation for device definition files"
```

---

### Task 3: Wpięcie rejestru w walidację konfiguracji

Po tym zadaniu `config.yaml` z własnym modelem przechodzi walidację cerberus.

**Uwaga na cache.** `_SCHEMA_CACHE` (`yaml_util.py:79`) żyje przez cały proces i **nie** sprawdza ponownie fingerprintu. Bez jawnego wyczyszczenia nowo zapisana definicja byłaby odrzucana przez walidację aż do restartu. Służy do tego istniejące `clear_config_cache(clear_static=True)` (`yaml_util.py:198`); używa go Task 6.

**Files:**
- Modify: `boneio/core/config/yaml_util.py:84-96` (`_get_modbus_device_models`), `boneio/core/config/yaml_util.py:1211-1234` (`load_config_from_file`)
- Modify: `boneio/core/utils/util.py:60-93` (`open_json`)
- Test: `tests/unit/core/test_custom_modbus_models.py`

**Interfaces:**
- Consumes: `device_registry.configure`, `device_registry.list_models`, `device_registry.load_model`, `device_registry.ModelNotFoundError`, `device_registry.BUILTIN_DIR` (Task 1)
- Produces: `open_json(path, model)` obsługuje własne definicje bez zmiany sygnatury; `load_config_from_file` konfiguruje rejestr na `<dirname(config_file)>/modbus_devices`

- [ ] **Step 1: Write the failing test**

Utwórz `tests/unit/core/test_custom_modbus_models.py`:

```python
"""Custom Modbus models must pass config validation like builtin ones."""

import json
import os

import pytest

from boneio.core.config.yaml_util import (
    ConfigurationException,
    clear_config_cache,
    load_config_from_string,
)
from boneio.modbus import device_registry

CONFIG_TEMPLATE = """
boneio:
  name: test
modbus:
  uart: uart4
modbus_devices:
  - id: mymeter
    address: 1
    model: {model}
"""


@pytest.fixture
def custom_dir(tmp_path):
    """Register a custom model directory and reset all caches around the test."""
    directory = tmp_path / "modbus_devices"
    directory.mkdir()
    with open(directory / "mycustommeter.json", "w") as fh:
        json.dump(
            {
                "model": "My Custom Meter",
                "registers_base": [
                    {
                        "base": 0,
                        "length": 1,
                        "register_type": "input",
                        "registers": [
                            {
                                "name": "Voltage",
                                "address": 0,
                                "unit_of_measurement": "V",
                                "state_class": "measurement",
                                "value_type": "S_WORD",
                            }
                        ],
                    }
                ],
            },
            fh,
        )
    device_registry.configure(str(directory))
    clear_config_cache(clear_static=True)
    yield str(directory)
    device_registry.configure(None)
    clear_config_cache(clear_static=True)


def test_custom_model_passes_validation(custom_dir):
    config = load_config_from_string(CONFIG_TEMPLATE.format(model="mycustommeter"))
    assert config["modbus_devices"][0]["model"] == "mycustommeter"


def test_builtin_model_still_passes_validation(custom_dir):
    config = load_config_from_string(CONFIG_TEMPLATE.format(model="sdm120"))
    assert config["modbus_devices"][0]["model"] == "sdm120"


def test_unknown_model_is_still_rejected(custom_dir):
    with pytest.raises(ConfigurationException):
        load_config_from_string(CONFIG_TEMPLATE.format(model="totally-unknown"))


def test_open_json_loads_custom_definition(custom_dir):
    from boneio.core.utils import open_json

    db = open_json(path=os.path.dirname(device_registry.BUILTIN_DIR), model="mycustommeter")
    assert db["model"] == "My Custom Meter"


def test_open_json_still_loads_builtin_definition(custom_dir):
    from boneio.core.utils import open_json

    db = open_json(path=os.path.dirname(device_registry.BUILTIN_DIR), model="sdm120")
    assert "registers_base" in db
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/core/test_custom_modbus_models.py -v`
Expected: FAIL — `test_custom_model_passes_validation` i `test_open_json_loads_custom_definition` padają (`ConfigurationException` / `FileNotFoundError`), bo ani schemat, ani `open_json` nie widzą katalogu użytkownika.

- [ ] **Step 3: Write minimal implementation**

W `boneio/core/config/yaml_util.py` zastąp ciało `_get_modbus_device_models` (linie 84-96):

```python
def _get_modbus_device_models() -> list[str]:
    """Return all model keys known to the device registry.

    Covers definitions shipped with the package and those provided by the user
    next to config.yaml.
    """
    from boneio.modbus import device_registry

    return sorted(ref.key for ref in device_registry.list_models())
```

W tym samym pliku, w `load_config_from_file`, przed próbą użycia cache (zaraz po `_t0 = _time.monotonic()`):

```python
    # Point the Modbus device registry at the user's definition directory
    # before anything validates or loads a model.
    from boneio.modbus import device_registry

    device_registry.configure(
        os.path.join(os.path.dirname(os.path.abspath(config_file)), "modbus_devices")
    )
```

W `boneio/core/utils/util.py` w `open_json`, przed dotychczasową logiką wyszukiwania po katalogu:

```python
    # Definitions may live outside the package (user-provided models), so ask
    # the registry first whenever the caller is looking in the package tree.
    from boneio.modbus import device_registry

    requested = os.path.normpath(path)
    if requested in (device_registry.BUILTIN_DIR, os.path.dirname(device_registry.BUILTIN_DIR)):
        try:
            return device_registry.load_model(model)
        except device_registry.ModelNotFoundError:
            pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/core/test_custom_modbus_models.py -v`
Expected: PASS (5 testów)

Potem regresja na sąsiednich obszarach:
Run: `.venv/bin/pytest tests/unit/core tests/unit/modbus -q`
Expected: PASS, bez nowych błędów

- [ ] **Step 5: Commit**

```bash
git add boneio/core/config/yaml_util.py boneio/core/utils/util.py tests/unit/core/test_custom_modbus_models.py
git commit -m "feat(modbus): accept user-provided device models in config validation"
```

---

### Task 4: Wpięcie rejestru w runtime i narzędzia

Koordynator, mock, endpoint dev-only i CLI przestają skanować katalog pakietu na własną rękę.

`boneio/webui/routes/dev_fake_device.py` korzysta z `_find_device_json` z `mock_coordinator`, więc naprawa jednej funkcji obsługuje oba miejsca.

**Files:**
- Modify: `boneio/modbus/coordinator.py:117-118`
- Modify: `boneio/modbus/mock_coordinator.py:38-52` (`_find_device_json`)
- Modify: `boneio/bonecli.py:63-92` (subparser `modbus`), `boneio/modbus/cli.py:158`
- Test: `tests/unit/modbus/test_registry_wiring.py`

**Interfaces:**
- Consumes: `device_registry.get_model_ref`, `device_registry.configure` (Task 1)
- Produces: `ModbusCoordinator._model_key: str` — klucz pliku definicji, używany przez `reload_modbus_model` w Task 5

- [ ] **Step 1: Write the failing test**

Utwórz `tests/unit/modbus/test_registry_wiring.py`:

```python
"""Runtime helpers must resolve models through the registry."""

import json
import os

import pytest

from boneio.modbus import device_registry
from boneio.modbus.mock_coordinator import _find_device_json


@pytest.fixture
def custom_dir(tmp_path):
    directory = tmp_path / "modbus_devices"
    directory.mkdir()
    with open(directory / "mycustommeter.json", "w") as fh:
        json.dump(
            {
                "model": "My Custom Meter",
                "registers_base": [
                    {
                        "base": 0,
                        "length": 1,
                        "register_type": "input",
                        "registers": [
                            {
                                "name": "Voltage",
                                "address": 0,
                                "unit_of_measurement": "V",
                                "state_class": "measurement",
                                "value_type": "S_WORD",
                            }
                        ],
                    }
                ],
            },
            fh,
        )
    device_registry.configure(str(directory))
    yield str(directory)
    device_registry.configure(None)


def test_find_device_json_resolves_custom_model(custom_dir):
    path = _find_device_json("mycustommeter")
    assert os.path.basename(str(path)) == "mycustommeter.json"


def test_find_device_json_still_resolves_builtin(custom_dir):
    path = _find_device_json("sdm120")
    assert os.path.basename(str(path)) == "sdm120.json"


def test_find_device_json_raises_for_unknown_model(custom_dir):
    with pytest.raises(FileNotFoundError):
        _find_device_json("no-such-model")


def test_modbus_cli_subcommand_accepts_config_path():
    from boneio.bonecli import get_arguments

    args = get_arguments(
        ["modbus", "--uart", "uart4", "--baudrate", "9600", "-c", "/tmp/x/config.yaml"]
    )
    assert args.config == "/tmp/x/config.yaml"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/modbus/test_registry_wiring.py -v`
Expected: FAIL — `test_find_device_json_resolves_custom_model` (`FileNotFoundError`) oraz `test_modbus_cli_subcommand_accepts_config_path` (brak argumentu `-c`).

Jeśli `get_arguments` nosi w `boneio/bonecli.py` inną nazwę, użyj faktycznej nazwy funkcji budującej parser — reszta testu bez zmian.

- [ ] **Step 3: Write minimal implementation**

`boneio/modbus/coordinator.py` — zamień linie 117-118 na:

```python
        from boneio.modbus import device_registry

        self._model_key = model
        self._db = device_registry.load_model(model)
        self._model = self._db[MODEL]
```

`boneio/modbus/mock_coordinator.py` — zastąp ciało `_find_device_json`:

```python
def _find_device_json(model_key: str) -> Path:
    """Return the path of the definition file for ``model_key``."""
    from boneio.modbus import device_registry

    try:
        return Path(device_registry.get_model_ref(model_key).path)
    except device_registry.ModelNotFoundError as err:
        available = sorted(ref.key for ref in device_registry.list_models())
        raise FileNotFoundError(
            f"Device JSON not found for model '{model_key}'. Available models: {available}"
        ) from err
```

`boneio/bonecli.py` — do subparsera `modbus` (po argumencie `--uart`) dodaj:

```python
    modbus_parser.add_argument(
        "-c",
        "--config",
        metavar="path_to_config_dir",
        default="./config.yaml",
        help="Config file, used to locate user-provided Modbus device definitions",
    )
```

...a w miejscu obsługi podkomendy `modbus`, przed utworzeniem `ModbusHelper`:

```python
        from boneio.modbus import device_registry

        device_registry.configure(
            os.path.join(os.path.dirname(os.path.abspath(args.config)), "modbus_devices")
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/modbus/test_registry_wiring.py -v`
Expected: PASS (4 testy)

Run: `.venv/bin/pytest tests/unit -q -m "not hardware"`
Expected: PASS — w szczególności `tests/unit/webui/test_mock_coordinator.py`, który ładuje wszystkie wbudowane modele przez `_find_device_json`

- [ ] **Step 5: Commit**

```bash
git add boneio/modbus/coordinator.py boneio/modbus/mock_coordinator.py boneio/bonecli.py tests/unit/modbus/test_registry_wiring.py
git commit -m "feat(modbus): resolve device models through the registry at runtime"
```

---

### Task 5: Celowane przeładowanie modelu

Edycja definicji nie zmienia `config.yaml`, więc istniejące `reload_modbus_devices()` (`core/manager/modbus.py:279`) jej nie zauważy — przebudowuje koordynator wyłącznie przy zmianie `area` albo `name`.

**Files:**
- Modify: `boneio/core/manager/modbus.py` (nowa metoda po `reload_modbus_devices`)
- Test: `tests/unit/modbus/test_reload_modbus_model.py`

**Interfaces:**
- Consumes: `ModbusCoordinator._model_key` (Task 4), `ManagerModbus._get_device_id_from_config` (`modbus.py:232`), `ManagerModbus._configure_modbus_coordinators` (`modbus.py:117`), `ManagerModbus._remove_modbus_ha_discovery_for_id`
- Produces: `async ManagerModbus.reload_modbus_model(model_key: str) -> list[str]` — zwraca ID przebudowanych koordynatorów

- [ ] **Step 1: Write the failing test**

Utwórz `tests/unit/modbus/test_reload_modbus_model.py`:

```python
"""Editing a definition must rebuild only the coordinators using that model."""

from unittest.mock import MagicMock

import pytest

from boneio.core.manager.modbus import ManagerModbus


class _FakeCoordinator:
    def __init__(self, model_key: str):
        self._model_key = model_key


def _make_manager(coordinators: dict, devices: list[dict]) -> ManagerModbus:
    manager = ManagerModbus.__new__(ManagerModbus)
    manager._modbus_coordinators = coordinators
    manager._modbus = MagicMock()
    manager._manager = MagicMock()
    manager._manager._config_helper.get_config.return_value = {"modbus_devices": devices}
    manager._remove_modbus_ha_discovery_for_id = MagicMock()
    return manager


async def test_rebuilds_only_coordinators_of_that_model():
    devices = [
        {"id": "meter1", "address": 1, "model": "mycustommeter"},
        {"id": "meter2", "address": 2, "model": "sdm120"},
    ]
    coordinators = {
        "meter1": _FakeCoordinator("mycustommeter"),
        "meter2": _FakeCoordinator("sdm120"),
    }
    manager = _make_manager(coordinators, devices)

    rebuilt_coordinator = MagicMock()
    manager._configure_modbus_coordinators = MagicMock(
        return_value={"meter1": rebuilt_coordinator}
    )

    reloaded = await manager.reload_modbus_model("mycustommeter")

    assert reloaded == ["meter1"]
    manager._remove_modbus_ha_discovery_for_id.assert_called_once_with("meter1")
    assert manager._modbus_coordinators["meter1"] is rebuilt_coordinator
    assert manager._modbus_coordinators["meter2"] is coordinators["meter2"]


async def test_unused_model_is_a_no_op():
    devices = [{"id": "meter2", "address": 2, "model": "sdm120"}]
    coordinators = {"meter2": _FakeCoordinator("sdm120")}
    manager = _make_manager(coordinators, devices)
    manager._configure_modbus_coordinators = MagicMock(return_value={})

    assert await manager.reload_modbus_model("mycustommeter") == []
    manager._configure_modbus_coordinators.assert_not_called()


async def test_failed_rebuild_reports_ids_and_does_not_raise():
    devices = [{"id": "meter1", "address": 1, "model": "mycustommeter"}]
    coordinators = {"meter1": _FakeCoordinator("mycustommeter")}
    manager = _make_manager(coordinators, devices)
    manager._configure_modbus_coordinators = MagicMock(side_effect=RuntimeError("boom"))

    # The definition file is already written at this point; a broken rebuild
    # must not propagate and undo the user's save.
    assert await manager.reload_modbus_model("mycustommeter") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/modbus/test_reload_modbus_model.py -v`
Expected: FAIL — `AttributeError: 'ManagerModbus' object has no attribute 'reload_modbus_model'`

- [ ] **Step 3: Write minimal implementation**

W `boneio/core/manager/modbus.py`, bezpośrednio po `reload_modbus_devices`:

```python
    async def reload_modbus_model(self, model_key: str) -> list[str]:
        """Rebuild coordinators whose definition file just changed.

        Editing a device definition does not touch config.yaml, so the
        config-diffing reload cannot see it. Returns the IDs that were rebuilt.
        """
        affected = [
            device_id
            for device_id, coordinator in self._modbus_coordinators.items()
            if getattr(coordinator, "_model_key", None) == model_key
        ]
        if not affected:
            _LOGGER.debug("No Modbus coordinators use model %s", model_key)
            return []

        config = self._manager._config_helper.get_config()
        configs_by_id = {
            self._get_device_id_from_config(device_config): device_config
            for device_config in config.get("modbus_devices", [])
        }
        configs_to_rebuild = [
            configs_by_id[device_id] for device_id in affected if device_id in configs_by_id
        ]
        if not configs_to_rebuild:
            return []

        for device_id in affected:
            self._remove_modbus_ha_discovery_for_id(device_id)
            self._modbus_coordinators.pop(device_id, None)

        await asyncio.sleep(1.5)  # let HA process the discovery removal

        try:
            new_coordinators = self._configure_modbus_coordinators(devices=configs_to_rebuild)
        except Exception as err:
            # The definition file is already saved; surface the problem through
            # the API response rather than failing the write.
            _LOGGER.error("Failed to rebuild coordinators for model %s: %s", model_key, err)
            return []

        self._modbus_coordinators.update(new_coordinators)
        for coordinator in new_coordinators.values():
            try:
                await coordinator.send_online_status()
            except Exception as err:
                _LOGGER.error(
                    "Failed to send online status for coordinator %s: %s", coordinator.id, err
                )

        _LOGGER.info(
            "Rebuilt %d Modbus coordinators for model %s", len(new_coordinators), model_key
        )
        return sorted(new_coordinators.keys())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/modbus/test_reload_modbus_model.py -v`
Expected: PASS (3 testy)

- [ ] **Step 5: Commit**

```bash
git add boneio/core/manager/modbus.py tests/unit/modbus/test_reload_modbus_model.py
git commit -m "feat(modbus): rebuild coordinators when a device definition changes"
```

---

### Task 6: Endpointy CRUD definicji

**Files:**
- Modify: `boneio/webui/routes/modbus.py` (modele żądań przy pozostałych, ok. linii 39-80; nowe endpointy po `get_model_entities`, ok. linii 640)
- Test: `tests/unit/webui/test_modbus_device_definitions.py`

**Interfaces:**
- Consumes: `device_registry` (Task 1), `validate_definition` (Task 2), `clear_config_cache` (Task 3), `ManagerModbus.reload_modbus_model` (Task 5), istniejące `get_manager` z `boneio/webui/routes/modbus.py:34`
- Produces: pięć operacji pod `/api/modbus/device_definitions`; frontend z Tasków 10-12 konsumuje kształty odpowiedzi opisane niżej

Kształty odpowiedzi:
- `GET /api/modbus/device_definitions` → `{"definitions": [{"key", "source", "model", "manufacturer", "description", "category", "default_address", "default_update_interval", "used_by": [str]}]}`
- `GET /api/modbus/device_definitions/{key}` → `{"key", "source", "definition": {...}}`
- `POST` / `PUT` → `{"key", "source": "custom", "reloaded": [str], "warning": str | None}`
- `DELETE` → `{"key", "deleted": true}`

- [ ] **Step 1: Write the failing test**

Utwórz `tests/unit/webui/test_modbus_device_definitions.py`:

```python
"""CRUD for user-provided Modbus device definitions."""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from boneio.modbus import device_registry

VALID_DEFINITION = {
    "model": "My Custom Meter",
    "manufacturer": "Acme",
    "description": "Test meter",
    "category": "energy_meters",
    "default_address": 1,
    "default_update_interval": "30s",
    "registers_base": [
        {
            "base": 0,
            "length": 1,
            "register_type": "input",
            "registers": [
                {
                    "name": "Voltage",
                    "address": 0,
                    "unit_of_measurement": "V",
                    "state_class": "measurement",
                    "value_type": "S_WORD",
                }
            ],
        }
    ],
}


def _make_client(manager):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from boneio.webui.routes.modbus import get_manager, router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_manager] = lambda: manager
    return TestClient(app)


@pytest.fixture
def manager():
    mgr = MagicMock()
    mgr.config_helper.get_config.return_value = {"modbus_devices": []}
    mgr.modbus.reload_modbus_model = AsyncMock(return_value=[])
    mgr.modbus._get_device_id_from_config.side_effect = lambda cfg: cfg["id"]
    return mgr


@pytest.fixture
def client(manager, tmp_path):
    directory = tmp_path / "modbus_devices"
    directory.mkdir()
    device_registry.configure(str(directory))
    yield _make_client(manager)
    device_registry.configure(None)


def test_create_writes_file_and_reloads(client, manager, tmp_path):
    response = client.post(
        "/api/modbus/device_definitions",
        json={"key": "mycustommeter", "definition": VALID_DEFINITION},
    )

    assert response.status_code == 200
    assert response.json()["source"] == "custom"
    written = tmp_path / "modbus_devices" / "mycustommeter.json"
    assert json.load(open(written))["model"] == "My Custom Meter"
    manager.modbus.reload_modbus_model.assert_awaited_once_with("mycustommeter")


def test_create_rejects_invalid_key(client):
    response = client.post(
        "/api/modbus/device_definitions",
        json={"key": "../escape", "definition": VALID_DEFINITION},
    )
    assert response.status_code == 400


def test_create_rejects_invalid_definition(client):
    response = client.post(
        "/api/modbus/device_definitions",
        json={"key": "broken", "definition": {"model": "No registers"}},
    )
    assert response.status_code == 422


def test_create_conflicts_with_builtin_key(client):
    response = client.post(
        "/api/modbus/device_definitions",
        json={"key": "sdm120", "definition": VALID_DEFINITION},
    )
    assert response.status_code == 409


def test_create_conflicts_with_existing_custom_key(client):
    client.post(
        "/api/modbus/device_definitions",
        json={"key": "mycustommeter", "definition": VALID_DEFINITION},
    )
    response = client.post(
        "/api/modbus/device_definitions",
        json={"key": "mycustommeter", "definition": VALID_DEFINITION},
    )
    assert response.status_code == 409


def test_update_overwrites_custom_definition(client):
    client.post(
        "/api/modbus/device_definitions",
        json={"key": "mycustommeter", "definition": VALID_DEFINITION},
    )
    changed = {**VALID_DEFINITION, "manufacturer": "Changed"}

    response = client.put(
        "/api/modbus/device_definitions/mycustommeter", json={"definition": changed}
    )

    assert response.status_code == 200
    read_back = client.get("/api/modbus/device_definitions/mycustommeter").json()
    assert read_back["definition"]["manufacturer"] == "Changed"


def test_update_refuses_builtin(client):
    response = client.put(
        "/api/modbus/device_definitions/sdm120", json={"definition": VALID_DEFINITION}
    )
    assert response.status_code == 403


def test_failed_reload_keeps_the_file_and_warns(client, manager, tmp_path):
    manager.modbus.reload_modbus_model = AsyncMock(side_effect=RuntimeError("boom"))

    response = client.post(
        "/api/modbus/device_definitions",
        json={"key": "mycustommeter", "definition": VALID_DEFINITION},
    )

    assert response.status_code == 200
    assert response.json()["warning"]
    assert (tmp_path / "modbus_devices" / "mycustommeter.json").exists()


def test_get_builtin_definition_is_readable_for_forking(client):
    response = client.get("/api/modbus/device_definitions/sdm120")
    assert response.status_code == 200
    assert response.json()["source"] == "builtin"
    assert "registers_base" in response.json()["definition"]


def test_list_reports_usage(client, manager):
    client.post(
        "/api/modbus/device_definitions",
        json={"key": "mycustommeter", "definition": VALID_DEFINITION},
    )
    manager.config_helper.get_config.return_value = {
        "modbus_devices": [{"id": "meter1", "address": 1, "model": "mycustommeter"}]
    }

    definitions = {d["key"]: d for d in client.get("/api/modbus/device_definitions").json()["definitions"]}

    assert definitions["mycustommeter"]["used_by"] == ["meter1"]
    assert definitions["mycustommeter"]["has_set_base"] is False
    assert definitions["sdm120"]["used_by"] == []


def test_delete_blocked_while_in_use(client, manager):
    client.post(
        "/api/modbus/device_definitions",
        json={"key": "mycustommeter", "definition": VALID_DEFINITION},
    )
    manager.config_helper.get_config.return_value = {
        "modbus_devices": [{"id": "meter1", "address": 1, "model": "mycustommeter"}]
    }

    response = client.delete("/api/modbus/device_definitions/mycustommeter")

    assert response.status_code == 409
    assert "meter1" in response.json()["detail"]


def test_delete_removes_unused_definition(client, tmp_path):
    client.post(
        "/api/modbus/device_definitions",
        json={"key": "mycustommeter", "definition": VALID_DEFINITION},
    )

    response = client.delete("/api/modbus/device_definitions/mycustommeter")

    assert response.status_code == 200
    assert not (tmp_path / "modbus_devices" / "mycustommeter.json").exists()


def test_delete_refuses_builtin(client):
    assert client.delete("/api/modbus/device_definitions/sdm120").status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/webui/test_modbus_device_definitions.py -v`
Expected: FAIL — wszystkie żądania zwracają 404, bo endpointy nie istnieją

- [ ] **Step 3: Write minimal implementation**

W `boneio/webui/routes/modbus.py` dopisz modele żądań obok pozostałych (przy `ModbusGetRequest`):

```python
class DeviceDefinitionCreateRequest(BaseModel):
    """Request model for creating a user-provided device definition."""

    key: str
    definition: dict


class DeviceDefinitionUpdateRequest(BaseModel):
    """Request model for overwriting a user-provided device definition."""

    definition: dict
```

Następnie po `get_model_entities` dodaj:

```python
def _definition_metadata(ref, definition: dict, used_by: list[str]) -> dict:
    """Shape a definition for the listing endpoint."""
    return {
        "key": ref.key,
        "source": ref.source,
        "model": definition.get("model", ref.key),
        "manufacturer": definition.get("manufacturer", ""),
        "description": definition.get("description", ""),
        "category": definition.get("category", ""),
        "default_address": definition.get("default_address", 1),
        "default_update_interval": definition.get("default_update_interval", "30s"),
        "has_set_base": bool(definition.get("set_base")),
        "used_by": used_by,
    }


def _usage_by_model(boneio_manager) -> dict[str, list[str]]:
    """Map model key -> IDs of configured devices using it."""
    usage: dict[str, list[str]] = {}
    config = boneio_manager.config_helper.get_config() or {}
    for device_config in config.get("modbus_devices", []) or []:
        model = device_config.get("model")
        if not model:
            continue
        device_id = boneio_manager.modbus._get_device_id_from_config(device_config)
        usage.setdefault(model, []).append(device_id)
    return usage


async def _write_definition(key: str, definition: dict, boneio_manager) -> dict:
    """Persist a validated definition and rebuild coordinators using it."""
    from boneio.core.config.yaml_util import clear_config_cache
    from boneio.modbus import device_registry

    path = device_registry.custom_path_for(key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(definition, fh, indent=2, ensure_ascii=False)

    device_registry.invalidate()
    # The in-process schema cache pins the allowed model list, so a new model
    # would be rejected by config validation until it is dropped.
    clear_config_cache(clear_static=True)

    warning = None
    reloaded: list[str] = []
    try:
        reloaded = await boneio_manager.modbus.reload_modbus_model(key)
    except Exception as err:
        _LOGGER.error("Reload after saving model %s failed: %s", key, err)
        warning = f"Definition saved, but reloading devices failed: {err}"

    return {"key": key, "source": "custom", "reloaded": reloaded, "warning": warning}


@router.get("/modbus/device_definitions")
async def list_device_definitions(boneio_manager: Manager = Depends(get_manager)):
    """List every known device definition with metadata and usage."""
    from boneio.modbus import device_registry

    usage = _usage_by_model(boneio_manager)
    definitions = []
    for ref in device_registry.list_models():
        try:
            with open(ref.path) as fh:
                data = json.load(fh)
        except Exception as exc:
            _LOGGER.warning("Skipping unreadable definition %s: %s", ref.path, exc)
            continue
        definitions.append(_definition_metadata(ref, data, usage.get(ref.key, [])))
    return {"definitions": definitions}


@router.get("/modbus/device_definitions/{key}")
async def get_device_definition(key: str):
    """Return the full definition for any model (used to fork a builtin)."""
    from boneio.modbus import device_registry

    try:
        ref = device_registry.get_model_ref(key)
        return {"key": key, "source": ref.source, "definition": device_registry.load_model(key)}
    except device_registry.ModelNotFoundError as err:
        raise HTTPException(status_code=404, detail=f"Model '{key}' not found") from err


@router.post("/modbus/device_definitions")
async def create_device_definition(
    request: DeviceDefinitionCreateRequest,
    boneio_manager: Manager = Depends(get_manager),
):
    """Create a new user-provided definition."""
    from pydantic import ValidationError

    from boneio.modbus import device_registry
    from boneio.modbus.device_definition import validate_definition

    if not device_registry.is_valid_key(request.key):
        raise HTTPException(
            status_code=400,
            detail="Model key must match ^[a-z0-9][a-z0-9_-]{1,63}$",
        )
    try:
        device_registry.get_model_ref(request.key)
    except device_registry.ModelNotFoundError:
        pass
    else:
        raise HTTPException(status_code=409, detail=f"Model '{request.key}' already exists")

    try:
        validate_definition(request.definition)
    except ValidationError as err:
        raise HTTPException(status_code=422, detail=err.errors()) from err

    return await _write_definition(request.key, request.definition, boneio_manager)


@router.put("/modbus/device_definitions/{key}")
async def update_device_definition(
    key: str,
    request: DeviceDefinitionUpdateRequest,
    boneio_manager: Manager = Depends(get_manager),
):
    """Overwrite an existing user-provided definition."""
    from pydantic import ValidationError

    from boneio.modbus import device_registry
    from boneio.modbus.device_definition import validate_definition

    try:
        ref = device_registry.get_model_ref(key)
    except device_registry.ModelNotFoundError as err:
        raise HTTPException(status_code=404, detail=f"Model '{key}' not found") from err
    if ref.source == "builtin":
        raise HTTPException(
            status_code=403,
            detail=f"'{key}' is a built-in model; save it under a different name instead",
        )

    try:
        validate_definition(request.definition)
    except ValidationError as err:
        raise HTTPException(status_code=422, detail=err.errors()) from err

    return await _write_definition(key, request.definition, boneio_manager)


@router.delete("/modbus/device_definitions/{key}")
async def delete_device_definition(key: str, boneio_manager: Manager = Depends(get_manager)):
    """Delete a user-provided definition that no configured device uses."""
    from boneio.core.config.yaml_util import clear_config_cache
    from boneio.modbus import device_registry

    try:
        ref = device_registry.get_model_ref(key)
    except device_registry.ModelNotFoundError as err:
        raise HTTPException(status_code=404, detail=f"Model '{key}' not found") from err
    if ref.source == "builtin":
        raise HTTPException(status_code=403, detail=f"'{key}' is a built-in model")

    used_by = _usage_by_model(boneio_manager).get(key, [])
    if used_by:
        raise HTTPException(
            status_code=409,
            detail=f"Model '{key}' is used by: {', '.join(used_by)}",
        )

    os.remove(ref.path)
    device_registry.invalidate()
    clear_config_cache(clear_static=True)
    return {"key": key, "deleted": True}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/webui/test_modbus_device_definitions.py -v`
Expected: PASS (14 testów)

- [ ] **Step 5: Commit**

```bash
git add boneio/webui/routes/modbus.py tests/unit/webui/test_modbus_device_definitions.py
git commit -m "feat(modbus): add CRUD API for user-provided device definitions"
```

---

### Task 7: Router `/schema` z listą modeli z rejestru

`/schema` jest dziś statycznym mountem z katalogu pakietu (`webui/app.py:796` oraz `:891`), więc edytor YAML zna wyłącznie modele z czasu builda i podświetla własny model jako błąd.

**Files:**
- Create: `boneio/webui/routes/schema.py`
- Modify: `boneio/webui/app.py:48-68` (import), `:147-160` (rejestracja routera), `:796` i `:891` (usunięcie mountów)
- Test: `tests/unit/webui/test_schema_router.py`

**Interfaces:**
- Consumes: `device_registry.list_models` (Task 1)
- Produces: `boneio.webui.routes.schema.router` — obsługuje `GET /schema/{filename}`

- [ ] **Step 1: Write the failing test**

Utwórz `tests/unit/webui/test_schema_router.py`:

```python
"""The served JSON schema must know about user-provided Modbus models."""

import json

import pytest

from boneio.modbus import device_registry


def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from boneio.webui.routes.schema import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def client(tmp_path):
    directory = tmp_path / "modbus_devices"
    directory.mkdir()
    with open(directory / "mycustommeter.json", "w") as fh:
        json.dump(
            {
                "model": "My Custom Meter",
                "registers_base": [
                    {
                        "base": 0,
                        "length": 1,
                        "register_type": "input",
                        "registers": [
                            {
                                "name": "Voltage",
                                "address": 0,
                                "unit_of_measurement": "V",
                                "state_class": "measurement",
                                "value_type": "S_WORD",
                            }
                        ],
                    }
                ],
            },
            fh,
        )
    device_registry.configure(str(directory))
    yield _client()
    device_registry.configure(None)


def _model_enums(node):
    """Collect every enum that belongs to a property named 'model'."""
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "model" and isinstance(value, dict) and "enum" in value:
                found.append(value["enum"])
            found.extend(_model_enums(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_model_enums(item))
    return found


def test_config_schema_includes_custom_model(client):
    schema = client.get("/schema/config.schema.json").json()
    enums = _model_enums(schema)
    assert enums, "no model enum found in served schema"
    assert any("mycustommeter" in enum for enum in enums)
    assert any("sdm120" in enum for enum in enums)


def test_section_schema_includes_custom_model(client):
    schema = client.get("/schema/modbus_devices.schema.json").json()
    enums = _model_enums(schema)
    assert any("mycustommeter" in enum for enum in enums)


def test_unknown_schema_file_is_404(client):
    assert client.get("/schema/nope.schema.json").status_code == 404


def test_path_traversal_is_rejected(client):
    assert client.get("/schema/..%2F..%2Fconfig.yaml").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/webui/test_schema_router.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'boneio.webui.routes.schema'`

- [ ] **Step 3: Write minimal implementation**

Utwórz `boneio/webui/routes/schema.py`:

```python
"""Serve JSON schema files with a live list of Modbus device models.

The schema files are generated at build time and therefore only know about
models shipped with the package. Patching the model enum on the way out lets
the config editor accept user-provided models.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

_LOGGER = logging.getLogger(__name__)

router = APIRouter()
SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"


def _available_files() -> set[str]:
    if not SCHEMA_DIR.is_dir():
        return set()
    return {path.name for path in SCHEMA_DIR.glob("*.schema.json")}


def _patch_model_enums(node, models: list[str]) -> None:
    """Replace every ``model`` property enum with the registry's model list."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "model" and isinstance(value, dict) and isinstance(value.get("enum"), list):
                value["enum"] = models
            _patch_model_enums(value, models)
    elif isinstance(node, list):
        for item in node:
            _patch_model_enums(item, models)


@router.get("/schema/{filename}")
async def serve_schema(filename: str):
    """Serve a generated JSON schema file, with live Modbus model list."""
    from boneio.modbus import device_registry

    if filename not in _available_files():
        raise HTTPException(status_code=404, detail=f"Schema '{filename}' not found")

    with open(SCHEMA_DIR / filename) as fh:
        schema = json.load(fh)

    _patch_model_enums(schema, sorted(ref.key for ref in device_registry.list_models()))

    return JSONResponse(schema, headers={"Cache-Control": "no-cache"})
```

W `boneio/webui/app.py`:

1. dopisz import obok pozostałych routerów: `from boneio.webui.routes.schema import router as schema_router`
2. dopisz rejestrację w bloku `include_router` (np. po `app.include_router(modbus_router)`): `app.include_router(schema_router)`
3. usuń oba mounty `/schema` — linię 796 `app.mount("/schema", StaticFiles(directory=f"{APP_DIR}/schema"), name="schema")` oraz linie 890-891 (`if (APP_DIR / "schema").exists():` wraz z jej mountem)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/webui/test_schema_router.py -v`
Expected: PASS (4 testy)

Run: `.venv/bin/python -c "import boneio.webui.app"`
Expected: brak błędów — mounty usunięte czysto

- [ ] **Step 5: Commit**

```bash
git add boneio/webui/routes/schema.py boneio/webui/app.py tests/unit/webui/test_schema_router.py
git commit -m "feat(modbus): serve config schema with live device model list"
```

---

### Task 8: Round-trip definicji bez strat (frontend, logika)

Dziś `parseDeviceConfig` (`types.ts:105`) zachowuje wyłącznie pola, które kreator umie edytować, a `groupRegistersIntoBlocks` (`types.ts:160`) buduje podział na bloki od zera. Wczytanie cudzego pliku i zapis skasowałyby encje sterujące oraz przepartycjonowały ręcznie dostrojony układ odczytów.

To zadanie jest czysto logiczne — bez zmian w komponentach.

**Files:**
- Modify: `frontend/src/components/ModbusDeviceCreator/types.ts`
- Test: `frontend/src/components/ModbusDeviceCreator/__tests__/roundTrip.test.ts`

**Interfaces:**
- Consumes: nic z wcześniejszych zadań (frontend niezależny od backendu do Taska 10)
- Produces:
  - `Register.passthrough?: Record<string, unknown>`
  - `CreatorState` rozszerzony o `manufacturer`, `description`, `defaultAddress`, `defaultUpdateInterval`, `passthrough`, `importedBlocks`
  - `parseDeviceConfig(config: DeviceConfig): CreatorState` (pełny stan, nie `Partial`)
  - `buildDeviceConfig(state: CreatorState): DeviceConfig`
  - `buildRegistersBase(registers: Register[], importedBlocks: OutputRegisterBlock[] | null): OutputRegisterBlock[]`
  - `emptyCreatorState(): CreatorState`

- [ ] **Step 1: Write the failing test**

Utwórz `frontend/src/components/ModbusDeviceCreator/__tests__/roundTrip.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import {
  parseDeviceConfig,
  buildDeviceConfig,
  emptyCreatorState,
  type DeviceConfig,
} from '../types';

const DEVICES_DIR = path.resolve(__dirname, '../../../../../boneio/modbus/devices');

function builtinDefinitionPaths(): string[] {
  const paths: string[] = [];
  for (const category of fs.readdirSync(DEVICES_DIR, { withFileTypes: true })) {
    if (!category.isDirectory() || category.name === '__pycache__') continue;
    const dir = path.join(DEVICES_DIR, category.name);
    for (const file of fs.readdirSync(dir)) {
      if (file.endsWith('.json')) paths.push(path.join(dir, file));
    }
  }
  return paths.sort();
}

const DEFINITION_PATHS = builtinDefinitionPaths();

describe('device definition round-trip', () => {
  it('finds the shipped definitions', () => {
    expect(DEFINITION_PATHS.length).toBeGreaterThanOrEqual(27);
  });

  it.each(DEFINITION_PATHS.map(p => [path.basename(p), p]))(
    'preserves %s through parse and rebuild',
    (_name, filePath) => {
      const original = JSON.parse(fs.readFileSync(filePath as string, 'utf8')) as DeviceConfig;
      const rebuilt = buildDeviceConfig(parseDeviceConfig(original));
      expect(rebuilt).toEqual(original);
    },
  );
});

describe('buildDeviceConfig', () => {
  it('emits metadata entered in the creator', () => {
    const state = {
      ...emptyCreatorState(),
      modelName: 'My Meter',
      manufacturer: 'Acme',
      description: 'Test',
      category: 'energy_meters',
      defaultAddress: 3,
      defaultUpdateInterval: '15s',
      registers: [
        {
          id: 'a',
          name: 'Voltage',
          address: 0,
          register_type: 'input',
          unit_of_measurement: 'V',
          state_class: 'measurement',
          device_class: 'voltage',
          value_type: 'S_WORD',
          filters: [],
        },
      ],
    };

    const config = buildDeviceConfig(state);

    expect(config.model).toBe('My Meter');
    expect(config.manufacturer).toBe('Acme');
    expect(config.default_address).toBe(3);
    expect(config.default_update_interval).toBe('15s');
    expect(config.registers_base[0].registers[0].device_class).toBe('voltage');
  });

  it('omits metadata that was left empty', () => {
    const config = buildDeviceConfig({
      ...emptyCreatorState(),
      modelName: 'Bare',
      registers: [
        {
          id: 'a',
          name: 'Voltage',
          address: 0,
          register_type: 'input',
          unit_of_measurement: 'V',
          state_class: 'measurement',
          device_class: '',
          value_type: 'S_WORD',
          filters: [],
        },
      ],
    });

    expect('manufacturer' in config).toBe(false);
    expect('additional_entities' in config).toBe(false);
  });

  it('regroups blocks once the register set changes', () => {
    const original = JSON.parse(
      fs.readFileSync(path.join(DEVICES_DIR, 'sensors', 'sht30.json'), 'utf8'),
    ) as DeviceConfig;
    const state = parseDeviceConfig(original);
    const trimmed = { ...state, registers: state.registers.slice(0, 1) };

    const rebuilt = buildDeviceConfig(trimmed);

    expect(rebuilt.registers_base.flatMap(b => b.registers)).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/ModbusDeviceCreator/__tests__/roundTrip.test.ts`
Expected: FAIL — `buildDeviceConfig` i `emptyCreatorState` nie istnieją

- [ ] **Step 3: Write minimal implementation**

W `frontend/src/components/ModbusDeviceCreator/types.ts`:

Rozszerz typy (`RegisterFilter`, `Register`, `OutputRegister`, `DeviceConfig`, `CreatorState`):

```ts
export interface RegisterFilter {
  multiply?: number;
  offset?: number;
  round?: number;
  firmware_version?: number;
}

export interface Register {
  id: string;
  name: string;
  address: number;
  register_type: string;
  unit_of_measurement: string;
  state_class: string;
  device_class: string;
  value_type: string;
  filters: RegisterFilter[];
  /** Fields the creator does not edit (write_address, entity_type, ...) — kept verbatim. */
  passthrough?: Record<string, unknown>;
  tested?: boolean;
  testResult?: string;
  testError?: string;
}

export interface OutputRegister {
  name: string;
  address: number;
  unit_of_measurement?: string;
  state_class?: string;
  device_class?: string;
  value_type: string;
  filters?: RegisterFilter[];
  [key: string]: unknown;
}

export interface OutputRegisterBlock {
  base: number;
  length: number;
  register_type?: string;
  update_every_n?: number;
  registers: OutputRegister[];
}

export interface DeviceConfig {
  model: string;
  manufacturer?: string;
  description?: string;
  category?: string;
  default_address?: number;
  default_update_interval?: string;
  set_base?: SetBase;
  registers_base: OutputRegisterBlock[];
  [key: string]: unknown;
}

export interface CreatorState {
  modelName: string;
  fileName: string;
  category: string;
  manufacturer: string;
  description: string;
  defaultAddress: number;
  defaultUpdateInterval: string;
  enableSetAddress: boolean;
  setAddressAddress: number;
  enableSetBaudrate: boolean;
  baudrateAddress: number;
  baudrateMappings: Record<string, number>;
  registers: Register[];
  /** Top-level fields the creator does not edit (e.g. additional_entities). */
  passthrough: Record<string, unknown>;
  /** Block layout of the imported file, reused while the register set is unchanged. */
  importedBlocks: OutputRegisterBlock[] | null;
}
```

Dopisz stałe i funkcje (zastępując dotychczasowy `parseDeviceConfig`):

```ts
const KNOWN_TOP_LEVEL_KEYS = [
  'model',
  'manufacturer',
  'description',
  'category',
  'default_address',
  'default_update_interval',
  'set_base',
  'registers_base',
];

const KNOWN_REGISTER_KEYS = [
  'name',
  'address',
  'unit_of_measurement',
  'state_class',
  'device_class',
  'value_type',
  'filters',
];

const DEFAULT_REGISTER_TYPE = 'input';

export const emptyCreatorState = (): CreatorState => ({
  modelName: '',
  fileName: '',
  category: 'sensors',
  manufacturer: '',
  description: '',
  defaultAddress: 1,
  defaultUpdateInterval: '30s',
  enableSetAddress: false,
  setAddressAddress: 256,
  enableSetBaudrate: false,
  baudrateAddress: 257,
  baudrateMappings: { '9600': 9600, '19200': 19200 },
  registers: [],
  passthrough: {},
  importedBlocks: null,
});

export const parseDeviceConfig = (config: DeviceConfig): CreatorState => {
  const state = emptyCreatorState();
  state.modelName = config.model;
  if (config.manufacturer !== undefined) state.manufacturer = config.manufacturer;
  if (config.description !== undefined) state.description = config.description;
  if (config.category !== undefined) state.category = config.category;
  if (config.default_address !== undefined) state.defaultAddress = config.default_address;
  if (config.default_update_interval !== undefined) {
    state.defaultUpdateInterval = config.default_update_interval;
  }

  for (const [key, value] of Object.entries(config)) {
    if (!KNOWN_TOP_LEVEL_KEYS.includes(key)) {
      state.passthrough[key] = value;
    }
  }

  if (config.set_base) {
    if (config.set_base.set_address_address !== undefined) {
      state.enableSetAddress = true;
      state.setAddressAddress = config.set_base.set_address_address;
    }
    if (config.set_base.set_baudrate) {
      state.enableSetBaudrate = true;
      state.baudrateAddress = config.set_base.set_baudrate.address;
      state.baudrateMappings = config.set_base.set_baudrate.possible_baudrates;
    }
  }

  for (const block of config.registers_base) {
    for (const reg of block.registers) {
      const passthrough: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(reg)) {
        if (!KNOWN_REGISTER_KEYS.includes(key)) passthrough[key] = value;
      }
      state.registers.push({
        id: generateId(),
        name: reg.name,
        address: reg.address,
        register_type: block.register_type ?? DEFAULT_REGISTER_TYPE,
        unit_of_measurement: reg.unit_of_measurement ?? '',
        state_class: reg.state_class ?? '',
        device_class: reg.device_class || '',
        value_type: reg.value_type,
        filters: reg.filters || [],
        ...(Object.keys(passthrough).length > 0 ? { passthrough } : {}),
      });
    }
  }

  state.importedBlocks = config.registers_base;
  return state;
};

const blockSignature = (blocks: OutputRegisterBlock[]): string =>
  blocks
    .flatMap(block =>
      block.registers.map(
        reg => `${block.register_type ?? DEFAULT_REGISTER_TYPE}:${reg.address}`,
      ),
    )
    .sort()
    .join('|');

export const buildRegistersBase = (
  registers: Register[],
  importedBlocks: OutputRegisterBlock[] | null,
): OutputRegisterBlock[] => {
  const regenerated = groupRegistersIntoBlocks(registers);
  if (!importedBlocks) return regenerated;
  if (blockSignature(importedBlocks) !== blockSignature(regenerated)) return regenerated;

  // Register set is unchanged, so keep the file's hand-tuned block layout
  // (base/length decide how many Modbus reads happen) and only refresh payloads.
  const byKey = new Map<string, OutputRegister>();
  for (const block of regenerated) {
    for (const reg of block.registers) {
      byKey.set(`${block.register_type ?? DEFAULT_REGISTER_TYPE}:${reg.address}`, reg);
    }
  }
  return importedBlocks.map(block => ({
    ...block,
    registers: block.registers.map(
      reg => byKey.get(`${block.register_type ?? DEFAULT_REGISTER_TYPE}:${reg.address}`) ?? reg,
    ),
  }));
};

export const buildDeviceConfig = (state: CreatorState): DeviceConfig => {
  const config: DeviceConfig = { model: state.modelName, registers_base: [] };

  if (state.manufacturer) config.manufacturer = state.manufacturer;
  if (state.description) config.description = state.description;
  if (state.category) config.category = state.category;
  if (state.defaultAddress) config.default_address = state.defaultAddress;
  if (state.defaultUpdateInterval) config.default_update_interval = state.defaultUpdateInterval;

  if (state.enableSetAddress || state.enableSetBaudrate) {
    const setBase: SetBase = {};
    if (state.enableSetAddress) setBase.set_address_address = state.setAddressAddress;
    if (state.enableSetBaudrate) {
      setBase.set_baudrate = {
        address: state.baudrateAddress,
        possible_baudrates: state.baudrateMappings,
      };
    }
    config.set_base = setBase;
  }

  config.registers_base = buildRegistersBase(state.registers, state.importedBlocks);

  for (const [key, value] of Object.entries(state.passthrough)) {
    config[key] = value;
  }

  return config;
};
```

W `groupRegistersIntoBlocks` rozszerz budowanie pojedynczego rejestru, żeby niósł `passthrough` i pomijał puste metadane:

```ts
        registers: group.map(reg => {
          const output: OutputRegister = {
            name: reg.name,
            address: reg.address,
            value_type: reg.value_type,
          };
          if (reg.unit_of_measurement) {
            output.unit_of_measurement = reg.unit_of_measurement;
          }
          if (reg.state_class) {
            output.state_class = reg.state_class;
          }
          if (reg.device_class) {
            output.device_class = reg.device_class;
          }
          if (reg.filters.length > 0) {
            output.filters = reg.filters;
          }
          return { ...output, ...(reg.passthrough ?? {}) };
        }),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/ModbusDeviceCreator/__tests__/roundTrip.test.ts`
Expected: PASS — wszystkie wbudowane definicje przechodzą round-trip

Jeśli któryś plik nie przechodzi, przyczyną jest brakujące pole w `KNOWN_*_KEYS` albo gubiona wartość — popraw `parseDeviceConfig`/`buildDeviceConfig`, **nie** wyłączaj pliku z testu.

Run: `cd frontend && npx tsc --noEmit`
Expected: brak błędów — `index.tsx` nadal używa starego `generateJSON`, ale typy muszą się spinać

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ModbusDeviceCreator/types.ts frontend/src/components/ModbusDeviceCreator/__tests__/roundTrip.test.ts
git commit -m "feat(modbus): preserve unedited fields and block layout in device creator"
```

---

### Task 9: Metadane w kreatorze

**Files:**
- Modify: `frontend/src/components/ModbusDeviceCreator/DeviceInfoSection.tsx`
- Modify: `frontend/src/components/ModbusDeviceCreator/index.tsx`
- Modify: `frontend/src/locales/pl/modbus_devices.json`, `frontend/src/locales/en/modbus_devices.json`

**Interfaces:**
- Consumes: `buildDeviceConfig`, `emptyCreatorState`, `parseDeviceConfig`, `CreatorState` (Task 8)
- Produces: kreator trzyma i emituje `manufacturer`, `description`, `defaultAddress`, `defaultUpdateInterval`, `passthrough`, `importedBlocks`

- [ ] **Step 1: Rozszerz `DeviceInfoSection` o nowe pola**

Dodaj do `DeviceInfoSectionProps` i do formularza cztery pola, w stylu istniejących (`input input-bordered`, etykieta przez `t()`):

```tsx
  manufacturer: string;
  setManufacturer: (value: string) => void;
  description: string;
  setDescription: (value: string) => void;
  defaultAddress: number;
  setDefaultAddress: (value: number) => void;
  defaultUpdateInterval: string;
  setDefaultUpdateInterval: (value: string) => void;
```

Pola tekstowe (`manufacturer`, `description`, `defaultUpdateInterval`) jako `<input type="text" className="input input-bordered">`, `defaultAddress` jako `<NumericInput>` — tak jak istniejące `testDeviceAddress`.

Klucze tłumaczeń: `modbus_creator.manufacturer`, `modbus_creator.description`, `modbus_creator.default_address`, `modbus_creator.default_update_interval`.

- [ ] **Step 2: Podepnij stan w `index.tsx`**

Dodaj stany `manufacturer`, `description`, `defaultAddress`, `defaultUpdateInterval`, `passthrough`, `importedBlocks`; dołóż je do obiektu zapisywanego w `localStorage` i do tablicy zależności `useEffect` auto-zapisu; przekaż propsy do `DeviceInfoSection`.

Zastąp `generateJSON` delegacją do funkcji z Taska 8:

```tsx
  const currentState = (): CreatorState => ({
    modelName,
    fileName,
    category,
    manufacturer,
    description,
    defaultAddress,
    defaultUpdateInterval,
    enableSetAddress,
    setAddressAddress,
    enableSetBaudrate,
    baudrateAddress,
    baudrateMappings,
    registers,
    passthrough,
    importedBlocks,
  });

  const generateJSON = (): DeviceConfig => buildDeviceConfig(currentState());
```

`loadFromState` uzupełnij o nowe pola, a `clearDraft` przestaw na `emptyCreatorState()`, żeby nie utrzymywać dwóch list wartości domyślnych.

- [ ] **Step 3: Dodaj tłumaczenia**

Do `frontend/src/locales/pl/modbus_devices.json` i `.../en/modbus_devices.json`, w sekcji `modbus_creator`:

```json
"manufacturer": "Producent",
"description": "Opis",
"default_address": "Domyślny adres",
"default_update_interval": "Domyślny interwał odczytu",
"unedited_fields_notice": "Ta definicja zawiera encje sterujące, których kreator nie edytuje — zostaną zachowane."
```

...oraz angielskie odpowiedniki (`Manufacturer`, `Description`, `Default address`, `Default update interval`, `This definition contains control entities the creator does not edit — they will be preserved.`).

- [ ] **Step 4: Zweryfikuj**

Run: `cd frontend && npx tsc --noEmit && npx vitest run src/components/ModbusDeviceCreator`
Expected: PASS, bez błędów typów

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ModbusDeviceCreator frontend/src/locales
git commit -m "feat(modbus): add device metadata fields to the creator"
```

---

### Task 10: Zapis i wczytywanie definicji w kreatorze

**Files:**
- Create: `frontend/src/hooks/useDeviceDefinitions.ts`
- Modify: `frontend/src/components/ModbusDeviceCreator/ActionsSection.tsx`
- Modify: `frontend/src/components/ModbusDeviceCreator/index.tsx`
- Modify: `frontend/src/locales/pl/modbus_devices.json`, `frontend/src/locales/en/modbus_devices.json`
- Test: `frontend/src/hooks/__tests__/useDeviceDefinitions.test.ts`

**Interfaces:**
- Consumes: endpointy z Taska 6; `buildDeviceConfig`, `parseDeviceConfig`, `CreatorState` (Task 8)
- Produces:
  ```ts
  export interface DefinitionSummary {
    key: string;
    source: 'builtin' | 'custom';
    model: string;
    manufacturer: string;
    description: string;
    category: string;
    default_address: number;
    default_update_interval: string;
    has_set_base: boolean;
    used_by: string[];
  }
  export const listDefinitions: () => Promise<DefinitionSummary[]>;
  export const getDefinition: (key: string) => Promise<{ key: string; source: string; definition: DeviceConfig }>;
  export const createDefinition: (key: string, definition: DeviceConfig) => Promise<SaveResult>;
  export const updateDefinition: (key: string, definition: DeviceConfig) => Promise<SaveResult>;
  export const deleteDefinition: (key: string) => Promise<void>;
  export const isValidModelKey: (key: string) => boolean;
  ```
  gdzie `SaveResult = { key: string; source: string; reloaded: string[]; warning: string | null }`

- [ ] **Step 1: Write the failing test**

Utwórz `frontend/src/hooks/__tests__/useDeviceDefinitions.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/api/axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

import axios from '@/api/axios';
import {
  listDefinitions,
  createDefinition,
  updateDefinition,
  deleteDefinition,
  isValidModelKey,
} from '../useDeviceDefinitions';

describe('model key validation', () => {
  it.each(['sdm120', 'my-meter', 'my_meter_2'])('accepts %s', key => {
    expect(isValidModelKey(key)).toBe(true);
  });

  it.each(['../escape', 'UPPER', 'with space', '', 'a'])('rejects %s', key => {
    expect(isValidModelKey(key)).toBe(false);
  });
});

describe('definition API', () => {
  beforeEach(() => {
    vi.mocked(axios.get).mockReset();
    vi.mocked(axios.post).mockReset();
    vi.mocked(axios.put).mockReset();
    vi.mocked(axios.delete).mockReset();
  });

  it('unwraps the definition list', async () => {
    vi.mocked(axios.get).mockResolvedValue({
      data: { definitions: [{ key: 'sdm120', source: 'builtin', used_by: [] }] },
    } as never);

    const definitions = await listDefinitions();

    expect(axios.get).toHaveBeenCalledWith('/api/modbus/device_definitions');
    expect(definitions[0].key).toBe('sdm120');
  });

  it('posts key and definition when creating', async () => {
    vi.mocked(axios.post).mockResolvedValue({ data: { key: 'mymeter' } } as never);

    await createDefinition('mymeter', { model: 'My Meter', registers_base: [] });

    expect(axios.post).toHaveBeenCalledWith('/api/modbus/device_definitions', {
      key: 'mymeter',
      definition: { model: 'My Meter', registers_base: [] },
    });
  });

  it('puts only the definition when updating', async () => {
    vi.mocked(axios.put).mockResolvedValue({ data: { key: 'mymeter' } } as never);

    await updateDefinition('mymeter', { model: 'My Meter', registers_base: [] });

    expect(axios.put).toHaveBeenCalledWith('/api/modbus/device_definitions/mymeter', {
      definition: { model: 'My Meter', registers_base: [] },
    });
  });

  it('deletes by key', async () => {
    vi.mocked(axios.delete).mockResolvedValue({ data: { deleted: true } } as never);

    await deleteDefinition('mymeter');

    expect(axios.delete).toHaveBeenCalledWith('/api/modbus/device_definitions/mymeter');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/hooks/__tests__/useDeviceDefinitions.test.ts`
Expected: FAIL — brak modułu `../useDeviceDefinitions`

- [ ] **Step 3: Write minimal implementation**

Utwórz `frontend/src/hooks/useDeviceDefinitions.ts`:

```ts
import axios from '@/api/axios';
import type { DeviceConfig } from '@/components/ModbusDeviceCreator/types';

/** Must stay in sync with MODEL_KEY_RE in boneio/modbus/device_registry.py */
const MODEL_KEY_RE = /^[a-z0-9][a-z0-9_-]{1,63}$/;

export interface DefinitionSummary {
  key: string;
  source: 'builtin' | 'custom';
  model: string;
  manufacturer: string;
  description: string;
  category: string;
  default_address: number;
  default_update_interval: string;
  has_set_base: boolean;
  used_by: string[];
}

export interface SaveResult {
  key: string;
  source: string;
  reloaded: string[];
  warning: string | null;
}

export const isValidModelKey = (key: string): boolean => MODEL_KEY_RE.test(key);

export const listDefinitions = async (): Promise<DefinitionSummary[]> => {
  const { data } = await axios.get('/api/modbus/device_definitions');
  return data.definitions;
};

export const getDefinition = async (
  key: string,
): Promise<{ key: string; source: string; definition: DeviceConfig }> => {
  const { data } = await axios.get(`/api/modbus/device_definitions/${key}`);
  return data;
};

export const createDefinition = async (
  key: string,
  definition: DeviceConfig,
): Promise<SaveResult> => {
  const { data } = await axios.post('/api/modbus/device_definitions', { key, definition });
  return data;
};

export const updateDefinition = async (
  key: string,
  definition: DeviceConfig,
): Promise<SaveResult> => {
  const { data } = await axios.put(`/api/modbus/device_definitions/${key}`, { definition });
  return data;
};

export const deleteDefinition = async (key: string): Promise<void> => {
  await axios.delete(`/api/modbus/device_definitions/${key}`);
};
```

- [ ] **Step 4: Podepnij zapis i wczytywanie w kreatorze**

`ModbusDeviceCreator` przestaje być komponentem bez propsów — dostaje interfejs, przez który rodzic zleca wczytanie definicji i dowiaduje się o zapisie:

```tsx
interface ModbusDeviceCreatorProps {
  /** Definition the parent wants loaded; `mode: 'fork'` clears the key so a save creates a copy. */
  loadRequest?: { key: string; mode: 'edit' | 'fork' } | null;
  onSaved?: () => void;
}
```

Wczytanie odpala się w `useEffect` na zmianę `loadRequest`, wołając `loadDefinition(loadRequest.key, loadRequest.mode === 'fork')`.

Dodaj stan `editingKey: string | null` (null = nowa definicja), `saving`, `saveError`, `saveWarning` oraz:

```tsx
  const saveToDevice = async () => {
    const key = fileName || modelName.toLowerCase().replace(/\s+/g, '-');
    if (!isValidModelKey(key)) {
      setSaveError(t('modbus_creator.invalid_key'));
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      const result = editingKey
        ? await updateDefinition(editingKey, generateJSON())
        : await createDefinition(key, generateJSON());
      setEditingKey(result.key);
      setSaveWarning(result.warning);
      localStorage.removeItem(STORAGE_KEY);
      onSaved?.();
    } catch (error) {
      setSaveError(extractApiError(error, t('modbus_creator.save_failed')));
    } finally {
      setSaving(false);
    }
  };

  const loadDefinition = async (key: string, asFork: boolean) => {
    const { definition } = await getDefinition(key);
    loadFromState(parseDeviceConfig(definition));
    setEditingKey(asFork ? null : key);
    setFileName(asFork ? '' : key);
  };
```

`extractApiError` odczytuje `error.response?.data?.detail` i sprowadza go do stringa (detale walidacji pydantic przychodzą jako lista) — zdefiniuj lokalnie w `index.tsx`.

Dodaj selektor „Wczytaj model" (lista z `listDefinitions()`, wbudowane wczytywane z `asFork = true`, własne z `asFork = false`) oraz przekaż do `ActionsSection` props `onSaveToDevice`, `saving`, `saveError`, `saveWarning`, `editingKey`. W `ActionsSection` dodaj przycisk `btn btn-primary` z etykietą `modbus_creator.save_to_device` (albo `modbus_creator.update_on_device`, gdy `editingKey`), aktywny tylko gdy `isValid`.

Gdy `passthrough.additional_entities` albo dowolny rejestr ma `passthrough`, wyświetl `alert alert-info` z `modbus_creator.unedited_fields_notice` (klucz dodany w Tasku 9).

Nowe klucze tłumaczeń (pl + en): `save_to_device`, `update_on_device`, `saving`, `saved`, `save_failed`, `invalid_key`, `load_model`, `load_builtin_as_copy`, `reloaded_devices`.

- [ ] **Step 5: Zweryfikuj i commituj**

Run: `cd frontend && npx tsc --noEmit && npx vitest run src/hooks src/components/ModbusDeviceCreator`
Expected: PASS

```bash
git add frontend/src/hooks frontend/src/components/ModbusDeviceCreator frontend/src/locales
git commit -m "feat(modbus): save and load device definitions from the creator"
```

---

### Task 11: Lista własnych definicji

**Files:**
- Create: `frontend/src/components/ModbusDeviceCreator/DefinitionList.tsx`
- Modify: `frontend/src/components/ModbusHelper.tsx:1195` (obok `<ModbusDeviceCreator />`)
- Modify: `frontend/src/locales/pl/modbus_devices.json`, `frontend/src/locales/en/modbus_devices.json`

**Interfaces:**
- Consumes: `listDefinitions`, `deleteDefinition`, `getDefinition`, `DefinitionSummary` (Task 10)
- Produces: `<DefinitionList onEdit={(key: string) => void} onFork={(key: string) => void} refreshToken={number} />`

- [ ] **Step 1: Zbuduj komponent**

`DefinitionList` pobiera `listDefinitions()` przy montowaniu i przy każdej zmianie `refreshToken`, filtruje `source === 'custom'` i renderuje tabelę (`table table-zebra`, jak `ModbusDeviceTable.tsx`) z kolumnami: klucz, model, producent, kategoria, „używane przez".

Akcje w wierszu:
- **Edytuj** → `onEdit(key)`
- **Duplikuj** → `onFork(key)`
- **Pobierz** → `getDefinition(key)` i zapis pliku przez `Blob`, tak jak `downloadJSON` w `index.tsx`
- **Usuń** → `deleteDefinition(key)` po potwierdzeniu; przycisk `disabled`, gdy `used_by.length > 0`, z `title` wymieniającym blokujące urządzenia

Gdy lista własnych definicji jest pusta, pokaż `modbus_creator.no_custom_definitions` zamiast pustej tabeli.

- [ ] **Step 2: Wepnij w `ModbusHelper`**

`ModbusHelper` trzyma oba stany komunikacji między listą a kreatorem — bez imperatywnych referencji:

```tsx
const [refreshToken, setRefreshToken] = useState(0);
const [loadRequest, setLoadRequest] = useState<{ key: string; mode: 'edit' | 'fork' } | null>(null);

<ModbusDeviceCreator
  loadRequest={loadRequest}
  onSaved={() => setRefreshToken(token => token + 1)}
/>
<DefinitionList
  refreshToken={refreshToken}
  onEdit={key => setLoadRequest({ key, mode: 'edit' })}
  onFork={key => setLoadRequest({ key, mode: 'fork' })}
/>
```

Po udanym usunięciu definicji `DefinitionList` odświeża się sam; kreator reaguje wyłącznie na `loadRequest`.

- [ ] **Step 3: Dodaj tłumaczenia**

Klucze (pl + en): `custom_definitions`, `no_custom_definitions`, `used_by`, `edit`, `duplicate`, `download`, `delete`, `delete_confirm`, `delete_blocked`.

- [ ] **Step 4: Zweryfikuj**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: build przechodzi

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ModbusDeviceCreator/DefinitionList.tsx frontend/src/components/ModbusHelper.tsx frontend/src/locales
git commit -m "feat(modbus): list and manage custom device definitions in the UI"
```

---

### Task 12: Katalog urządzeń z runtime

Kreator urządzeń czyta dziś statyczny `MODBUS_DEVICE_CATALOG` z builda, więc własne modele w nim nie występują.

**Files:**
- Create: `frontend/src/hooks/useModbusCatalog.ts`
- Modify: `frontend/src/components/UISettings/AddModbusDeviceWizard.tsx:189-194`
- Modify: `frontend/src/components/ModbusHelper.tsx:1224`
- Test: `frontend/src/hooks/__tests__/useModbusCatalog.test.ts`

**Interfaces:**
- Consumes: `listDefinitions`, `DefinitionSummary` (Task 10); `MODBUS_DEVICE_CATALOG`, `ModbusDeviceInfo` (`frontend/src/generated/modbusDeviceCatalog.ts`)
- Produces:
  - `mergeCatalog(definitions: DefinitionSummary[]): Record<string, CatalogEntry>` — funkcja czysta, testowalna
  - `useModbusCatalog(): { catalog: Record<string, CatalogEntry>; loading: boolean; error: string | null }`
  - `CatalogEntry = ModbusDeviceInfo & { source: 'builtin' | 'custom' }`

- [ ] **Step 1: Write the failing test**

Utwórz `frontend/src/hooks/__tests__/useModbusCatalog.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { mergeCatalog } from '../useModbusCatalog';
import type { DefinitionSummary } from '../useDeviceDefinitions';

const definition = (overrides: Partial<DefinitionSummary>): DefinitionSummary => ({
  key: 'mymeter',
  source: 'custom',
  model: 'My Meter',
  manufacturer: 'Acme',
  description: 'Test meter',
  category: 'energy_meters',
  default_address: 2,
  default_update_interval: '15s',
  has_set_base: false,
  used_by: [],
  ...overrides,
});

describe('mergeCatalog', () => {
  it('adds custom definitions to the catalog', () => {
    const catalog = mergeCatalog([definition({})]);

    expect(catalog['mymeter'].displayName).toBe('My Meter');
    expect(catalog['mymeter'].source).toBe('custom');
    expect(catalog['mymeter'].defaultAddress).toBe(2);
    expect(catalog['mymeter'].defaultUpdateInterval).toBe('15s');
  });

  it('keeps builtin entries and marks their source', () => {
    const catalog = mergeCatalog([
      definition({ key: 'sdm120', source: 'builtin', model: 'SDM120' }),
    ]);

    expect(catalog['sdm120'].source).toBe('builtin');
  });

  it('falls back to the generated catalog when given nothing', () => {
    const catalog = mergeCatalog([]);

    expect(catalog['sdm120']).toBeDefined();
    expect(catalog['sdm120'].source).toBe('builtin');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/hooks/__tests__/useModbusCatalog.test.ts`
Expected: FAIL — brak modułu `../useModbusCatalog`

- [ ] **Step 3: Write minimal implementation**

Utwórz `frontend/src/hooks/useModbusCatalog.ts`:

```ts
import { useEffect, useState } from 'react';
import { MODBUS_DEVICE_CATALOG, type ModbusDeviceInfo } from '@/generated/modbusDeviceCatalog';
import { listDefinitions, type DefinitionSummary } from './useDeviceDefinitions';

export type CatalogEntry = ModbusDeviceInfo & { source: 'builtin' | 'custom' };

const staticCatalog = (): Record<string, CatalogEntry> =>
  Object.fromEntries(
    Object.entries(MODBUS_DEVICE_CATALOG).map(([key, info]) => [
      key,
      { ...info, source: 'builtin' as const },
    ]),
  );

/** Merge runtime definitions over the catalog generated at build time. */
export const mergeCatalog = (definitions: DefinitionSummary[]): Record<string, CatalogEntry> => {
  const catalog = staticCatalog();
  for (const definition of definitions) {
    catalog[definition.key] = {
      modelKey: definition.key,
      displayName: definition.model || definition.key,
      manufacturer: definition.manufacturer || '',
      description: definition.description || '',
      category: definition.category || 'other',
      defaultAddress: definition.default_address ?? 1,
      defaultUpdateInterval: definition.default_update_interval || '30s',
      hasSetBase: definition.has_set_base,
      source: definition.source,
    };
  }
  return catalog;
};

export const useModbusCatalog = () => {
  const [catalog, setCatalog] = useState<Record<string, CatalogEntry>>(staticCatalog);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listDefinitions()
      .then(definitions => {
        if (!cancelled) setCatalog(mergeCatalog(definitions));
      })
      .catch(() => {
        // Keep the build-time catalog so the picker still works offline.
        if (!cancelled) setError('catalog_fetch_failed');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { catalog, loading, error };
};
```

- [ ] **Step 4: Przełącz konsumentów**

W `AddModbusDeviceWizard.tsx` zastąp import `MODBUS_DEVICE_CATALOG` wywołaniem `const { catalog } = useModbusCatalog();`, a `Object.values(MODBUS_DEVICE_CATALOG)` w liniach 189 i 194 — `Object.values(catalog)`. Przy wpisach z `source === 'custom'` renderuj badge `badge badge-outline` z etykietą `modbus_creator.custom_badge`.

To samo w `ModbusHelper.tsx:1224`.

`MODBUS_CATEGORIES` z wygenerowanego pliku zastąp kategoriami wyliczonymi z `catalog`, żeby kategoria własnego urządzenia nie wypadła z filtra.

Run: `cd frontend && npx vitest run src/hooks src/components/UISettings/__tests__/modbusWizard.test.ts`
Expected: PASS — `modbusWizard.test.ts` testuje wygenerowany katalog i musi przejść bez zmian

- [ ] **Step 5: Zweryfikuj i commituj**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: build przechodzi

```bash
git add frontend/src/hooks frontend/src/components/UISettings/AddModbusDeviceWizard.tsx frontend/src/components/ModbusHelper.tsx frontend/src/locales
git commit -m "feat(modbus): show user-provided devices in the device picker"
```

---

### Task 13: Dokumentacja i test dymny end-to-end

**Files:**
- Create: `docs/MODBUS_CUSTOM_DEVICES.md`
- Modify: `README.md` (odnośnik w spisie dokumentacji, jeśli taki istnieje)

- [ ] **Step 1: Napisz dokument**

`docs/MODBUS_CUSTOM_DEVICES.md` ma pokryć:

- gdzie leżą definicje: `<katalog config.yaml>/modbus_devices/<klucz>.json`, i że przeżywają aktualizację pakietu
- zasady nazewnictwa klucza (`^[a-z0-9][a-z0-9_-]{1,63}$`) i to, że klucz jest nazwą używaną w `model:` w `config.yaml`
- format pliku z opisem pól (`model`, `manufacturer`, `description`, `category`, `default_address`, `default_update_interval`, `registers_base`, `set_base`, `additional_entities`) i kompletnym przykładem czujnika dwurejestrowego
- ścieżkę „fork wbudowanego": wczytaj model w kreatorze, zapisz pod nową nazwą
- ograniczenie: kreator nie edytuje encji zapisywalnych i pochodnych, ale je zachowuje przy imporcie i zapisie
- że usunięcie definicji używanej w `config.yaml` jest zablokowane i jak to odblokować

- [ ] **Step 2: Test dymny na żywym urządzeniu**

Wykonaj ręcznie i zanotuj wynik w opisie PR:

1. W WebUI otwórz kreator, zbuduj definicję z dwoma rejestrami, zapisz na urządzeniu
2. Sprawdź, że plik pojawił się w `<katalog config.yaml>/modbus_devices/`
3. W kreatorze urządzeń dodaj urządzenie na tym modelu — musi być widoczne na liście z oznaczeniem „własne"
4. Otwórz edytor YAML — model nie może być podświetlony jako błędny
5. Zmień w definicji `multiply` jednego rejestru i zapisz — wartość w dashboardzie zmienia się bez restartu usługi
6. Spróbuj usunąć definicję — operacja musi zostać zablokowana z nazwą urządzenia
7. Usuń urządzenie z konfiguracji, usuń definicję — teraz musi się udać

- [ ] **Step 3: Commit**

```bash
git add docs/MODBUS_CUSTOM_DEVICES.md README.md
git commit -m "docs(modbus): document user-provided device definitions"
```
