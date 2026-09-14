import pytest
from pydantic import ValidationError

from boneio.extensions.manifest import ExtensionManifest


def test_app_requires_a_pinned_container_runtime():
    manifest = ExtensionManifest.model_validate({
        "id": "community.zigbee2mqtt",
        "name": "Zigbee2MQTT",
        "version": "1.0.0",
        "type": "app",
        "permissions": {"network": True, "mqtt": True, "serial_devices": ["/dev/ttyUSB0"]},
        "runtime": {"image": "koenkk/zigbee2mqtt:2.0.0"},
    })
    assert manifest.runtime is not None


def test_app_rejects_latest_and_non_app_rejects_runtime():
    with pytest.raises(ValidationError):
        ExtensionManifest.model_validate({"id": "community.bad", "name": "Bad", "version": "1.0.0", "type": "app", "runtime": {"image": "repo/app:latest"}})
    with pytest.raises(ValidationError):
        ExtensionManifest.model_validate({"id": "community.modbus", "name": "Modbus", "version": "1.0.0", "type": "modbus_device_pack", "runtime": {"image": "repo/app:1.0.0"}})
