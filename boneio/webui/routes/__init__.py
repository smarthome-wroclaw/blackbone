"""Lazily exposed route objects.

Focused tools and tests can import one router without loading hardware-specific
manager modules. The application still resolves every listed router at startup.
"""

from __future__ import annotations

from importlib import import_module

_ROUTERS = {
    "addons_router": "addons",
    "auth_router": "auth",
    "caddy_router": "caddy",
    "can_router": "can",
    "config_router": "config",
    "covers_router": "covers",
    "dashboard_router": "dashboard",
    "dev_fake_device_router": "dev_fake_device",
    "irrigation_router": "irrigation",
    "migrations_router": "migrations",
    "modbus_router": "modbus",
    "mqtt_reference_router": "mqtt_reference",
    "mqtt_topics_router": "mqtt_topics",
    "nodered_router": "nodered",
    "outputs_router": "outputs",
    "remote_devices_router": "remote_devices",
    "schema_router": "schema",
    "sensors_router": "sensors",
    "system_router": "system",
    "templates_router": "templates",
    "tools_router": "tools",
    "update_router": "update",
}

__all__ = list(_ROUTERS)


def __getattr__(name: str):
    module_name = _ROUTERS.get(name)
    if module_name is None:
        raise AttributeError(name)
    value = import_module(f"{__name__}.{module_name}").router
    globals()[name] = value
    return value
