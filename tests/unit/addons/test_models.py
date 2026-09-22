from __future__ import annotations

import pytest
from pydantic import ValidationError

from boneio.addons.models import AddonManifest


def manifest(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "id": "community.example-meter",
        "name": "Example meter",
        "version": "1.0.0",
        "type": "modbus_device_pack",
        "blackbone": {"version": ">=0.1.0,<1.0.0"},
        "author": {"name": "Maintainer"},
        "license": "MIT",
        "files": [{"path": "modbus_devices/example-meter.json", "sha256": "a" * 64}],
    }
    value.update(changes)
    return value


def test_manifest_v1_accepts_only_declarative_pack_fields() -> None:
    assert AddonManifest.model_validate(manifest()).id == "community.example-meter"
    for forbidden in ("command", "image", "environment", "devices", "entrypoint"):
        with pytest.raises(ValidationError):
            AddonManifest.model_validate(manifest(**{forbidden: "unsafe"}))


@pytest.mark.parametrize(
    "path",
    ["/tmp/model.json", "../model.json", "modbus_devices//model.json", "other/model.json", "modbus_devices/model.exe"],
)
def test_manifest_rejects_unsafe_or_unmapped_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        AddonManifest.model_validate(manifest(files=[{"path": path, "sha256": "a" * 64}]))


def test_manifest_rejects_case_folded_collisions() -> None:
    with pytest.raises(ValidationError):
        AddonManifest.model_validate(
            manifest(
                files=[
                    {"path": "modbus_devices/Meter.json", "sha256": "a" * 64},
                    {"path": "modbus_devices/meter.json", "sha256": "b" * 64},
                ]
            )
        )


@pytest.mark.parametrize("version", ["1", "1.2", "01.2.3", "1.2.3-RC1", "1!1.2.3", "1.2.3+local", "1.2.3.dev1"])
def test_manifest_rejects_noncanonical_or_unpinned_versions(version: str) -> None:
    with pytest.raises(ValidationError):
        AddonManifest.model_validate(manifest(version=version))
