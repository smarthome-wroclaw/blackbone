"""Tests for safe declarative add-on installation."""

from __future__ import annotations

import hashlib
import json

import pytest
import yaml

from boneio.addons.service import AddonError, AddonService


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _registry_payloads(repository: str, destination: str = "modbus_devices/community.demo/demo.json") -> dict[str, bytes]:
    device = json.dumps({"model": "Community Demo Meter", "registers_base": []}).encode()
    manifest = yaml.safe_dump({
        "schema_version": 1,
        "id": "community.demo",
        "name": "Community demo",
        "version": "1.0.0",
        "type": "modbus_device_pack",
        "blackbone": {"min_version": "0.0.0"},
        "files": [{"source": "addons/demo/device.json", "destination": destination, "sha256": _sha(device)}],
    }).encode()
    index = json.dumps({"schema_version": 1, "addons": [{
        "id": "community.demo",
        "name": "Community demo",
        "version": "1.0.0",
        "type": "modbus_device_pack",
        "manifest_url": "addons/demo/addon.yaml",
        "manifest_sha256": _sha(manifest),
    }]}).encode()
    return {
        f"{repository}/index.json": index,
        f"{repository}/addons/demo/addon.yaml": manifest,
        f"{repository}/addons/demo/device.json": device,
    }


def test_installs_a_valid_device_pack(tmp_path, monkeypatch):
    repository = "https://addons.example.test"
    payloads = _registry_payloads(repository)
    monkeypatch.setattr(AddonService, "_download_bytes", staticmethod(payloads.__getitem__))
    service = AddonService(tmp_path)
    service.add_repository(repository)

    installed = service.install("community.demo", repository, "1.0.0")

    target = tmp_path / "modbus_devices/community.demo/demo.json"
    assert installed["id"] == "community.demo"
    assert target.exists()
    assert service.list_state()["installed"][0]["files"] == ["modbus_devices/community.demo/demo.json"]


def test_rejects_a_destination_outside_the_addon_directory(tmp_path, monkeypatch):
    repository = "https://addons.example.test"
    payloads = _registry_payloads(repository, "modbus_devices/other-owner/demo.json")
    monkeypatch.setattr(AddonService, "_download_bytes", staticmethod(payloads.__getitem__))
    service = AddonService(tmp_path)
    service.add_repository(repository)

    with pytest.raises(AddonError, match="own directory"):
        service.install("community.demo", repository, "1.0.0")


def test_rejects_a_core_model_collision(tmp_path, monkeypatch):
    repository = "https://addons.example.test"
    payloads = _registry_payloads(repository)
    device_url = f"{repository}/addons/demo/device.json"
    payloads[device_url] = json.dumps({"model": "SDM120", "registers_base": []}).encode()
    # Update checksums after changing the fixture's device body.
    manifest_url = f"{repository}/addons/demo/addon.yaml"
    manifest = yaml.safe_load(payloads[manifest_url])
    manifest["files"][0]["sha256"] = _sha(payloads[device_url])
    payloads[manifest_url] = yaml.safe_dump(manifest).encode()
    index_url = f"{repository}/index.json"
    index = json.loads(payloads[index_url])
    index["addons"][0]["manifest_sha256"] = _sha(payloads[manifest_url])
    payloads[index_url] = json.dumps(index).encode()
    monkeypatch.setattr(AddonService, "_download_bytes", staticmethod(payloads.__getitem__))
    service = AddonService(tmp_path)
    service.add_repository(repository)

    with pytest.raises(AddonError, match="already provided"):
        service.install("community.demo", repository, "1.0.0")
