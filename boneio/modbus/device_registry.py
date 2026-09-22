"""Registry for built-in and user-provided Modbus device definitions."""

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
    """Raised when no definition exists for a model key."""


@dataclass(frozen=True)
class ModelRef:
    key: str
    path: str
    source: str


_lock = threading.RLock()
_custom_dir: str | None = None
_addon_roots: dict[str, str] = {}
_builtin_index: dict[str, str] | None = None
_custom_index: dict[str, str] | None = None
_addon_index: dict[str, ModelRef] | None = None
_custom_stamp: tuple[int, int] | None = None


def is_valid_key(key: str) -> bool:
    return bool(MODEL_KEY_RE.fullmatch(key or ""))


def configure(custom_dir: str | None, addon_roots: dict[str, str] | None = None) -> None:
    """Configure user definitions and enabled, read-only add-on roots."""
    global _custom_dir, _addon_roots, _custom_index, _addon_index, _custom_stamp
    with _lock:
        _custom_dir = os.path.normpath(custom_dir) if custom_dir else None
        _addon_roots = {addon_id: os.path.normpath(root) for addon_id, root in (addon_roots or {}).items()}
        _custom_index = None
        _addon_index = None
        _custom_stamp = None


def configure_from_config(config_file: str) -> None:
    """Configure all definition sources from the active config directory."""
    config_dir = os.path.dirname(os.path.abspath(config_file))
    roots: dict[str, str] = {}
    state_path = os.path.join(config_dir, "addons", "state.json")
    try:
        with open(state_path, encoding="utf-8") as handle:
            installed = json.load(handle).get("installed", {})
        for addon_id, item in installed.items():
            if item.get("enabled") is True and isinstance(item.get("version"), str):
                roots[addon_id] = os.path.join(
                    config_dir,
                    "addons",
                    "installed",
                    addon_id,
                    item["version"],
                    "files",
                    "modbus_devices",
                )
    except (OSError, AttributeError, json.JSONDecodeError):
        roots = {}
    configure(os.path.join(config_dir, "modbus_devices"), roots)


def get_custom_dir() -> str | None:
    return _custom_dir


def invalidate() -> None:
    global _custom_index, _addon_index, _custom_stamp
    with _lock:
        _custom_index = _custom_stamp = None
        _addon_index = None


def custom_path_for(key: str) -> str:
    if not is_valid_key(key):
        raise ValueError(f"Invalid model key: {key!r}")
    if not _custom_dir:
        raise ValueError("Custom Modbus device directory is not configured")
    return os.path.join(_custom_dir, f"{key}.json")


def _scan(directory: str, recursive: bool) -> dict[str, str]:
    result: dict[str, str] = {}
    if not os.path.isdir(directory):
        return result
    if recursive:
        walker = os.walk(directory)
    else:
        walker = [(directory, [], os.listdir(directory))]
    for root, dirs, files in walker:
        dirs[:] = [name for name in dirs if name != "__pycache__"]
        for filename in files:
            if filename.endswith(".json") and is_valid_key(filename[:-5]):
                result.setdefault(filename[:-5], os.path.join(root, filename))
    return result


def _builtins() -> dict[str, str]:
    global _builtin_index
    with _lock:
        if _builtin_index is None:
            _builtin_index = _scan(BUILTIN_DIR, recursive=True)
        return _builtin_index


def _customs() -> dict[str, str]:
    global _custom_index, _custom_stamp
    with _lock:
        if not _custom_dir or not os.path.isdir(_custom_dir):
            _custom_index = {}
            return _custom_index
        stat = os.stat(_custom_dir)
        stamp = (stat.st_mtime_ns, stat.st_size)
        if _custom_index is None or stamp != _custom_stamp:
            _custom_index = _scan(_custom_dir, recursive=False)
            _custom_stamp = stamp
        return _custom_index


def _addons() -> dict[str, ModelRef]:
    global _addon_index
    with _lock:
        if _addon_index is None:
            result: dict[str, ModelRef] = {}
            for addon_id, root in sorted(_addon_roots.items()):
                for key, path in _scan(root, recursive=False).items():
                    result.setdefault(key, ModelRef(key, path, f"addon:{addon_id}"))
            _addon_index = result
        return _addon_index


def list_models() -> list[ModelRef]:
    builtins, customs, addons = _builtins(), _customs(), _addons()
    refs = [ModelRef(key, path, "builtin") for key, path in builtins.items()]
    for key, path in customs.items():
        if key in builtins:
            _LOGGER.warning("Custom Modbus definition %s shadows a built-in model and is ignored", key)
        else:
            refs.append(ModelRef(key, path, "custom"))
    occupied = set(builtins) | set(customs)
    for key, ref in addons.items():
        if key in occupied:
            _LOGGER.warning("Add-on Modbus definition %s conflicts with another source and is ignored", key)
        else:
            refs.append(ref)
            occupied.add(key)
    return sorted(refs, key=lambda ref: ref.key)


def get_model_ref(key: str) -> ModelRef:
    for ref in list_models():
        if ref.key == key:
            return ref
    raise ModelNotFoundError(f"Modbus model '{key}' not found")


def load_model(key: str) -> dict:
    with open(get_model_ref(key).path, encoding="utf-8") as file:
        return json.load(file)
