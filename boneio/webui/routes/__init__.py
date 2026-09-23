"""Lazily exposed route objects.

<<<<<<< ours
Focused tools and tests can import one router without loading hardware-specific
manager modules. The application still resolves every listed router at startup.
"""
=======
from boneio.webui.routes.accounts import router as accounts_router
from boneio.webui.routes.auth import router as auth_router
from boneio.webui.routes.caddy import router as caddy_router
from boneio.webui.routes.can import router as can_router
from boneio.webui.routes.config import router as config_router
from boneio.webui.routes.covers import router as covers_router
from boneio.webui.routes.dashboard import router as dashboard_router
from boneio.webui.routes.irrigation import router as irrigation_router
from boneio.webui.routes.migrations import router as migrations_router
from boneio.webui.routes.modbus import router as modbus_router
from boneio.webui.routes.nodered import router as nodered_router
from boneio.webui.routes.onboarding import router as onboarding_router
from boneio.webui.routes.mqtt_reference import router as mqtt_reference_router
from boneio.webui.routes.outputs import router as outputs_router
from boneio.webui.routes.remote_devices import router as remote_devices_router
from boneio.webui.routes.sensors import router as sensors_router
from boneio.webui.routes.system import router as system_router
from boneio.webui.routes.templates import router as templates_router
from boneio.webui.routes.tools import router as tools_router
from boneio.webui.routes.update import router as update_router
>>>>>>> theirs

from __future__ import annotations

<<<<<<< ours
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
=======
__all__ = [
    "accounts_router",
    "auth_router",
    "caddy_router",
    "can_router",
    "config_router",
    "covers_router",
    "dashboard_router",
    "dev_fake_device_router",
    "irrigation_router",
    "migrations_router",
    "modbus_router",
    "nodered_router",
    "onboarding_router",
    "mqtt_reference_router",
    "outputs_router",
    "remote_devices_router",
    "sensors_router",
    "system_router",
    "tools_router",
    "templates_router",
    "update_router",
]
>>>>>>> theirs
