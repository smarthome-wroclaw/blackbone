from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from boneio.addons.errors import AddonError
from boneio.addons.models import (
    IndexAddon,
    OperationStage,
    OperationType,
    Repository,
    RepositoryIndex,
    RepositoryState,
    RepositoryTrust,
)
from boneio.addons.network import FetchResult
from boneio.addons.service import AddonService


class FakeFetcher:
    def __init__(self, payloads: dict[str, bytes]) -> None:
        self.payloads = payloads

    async def fetch(self, url: str, *, limit: int, etag: str | None = None) -> FetchResult:
        payload = self.payloads.get(url)
        if payload is None:
            raise AddonError("repository_unavailable", "Missing fake URL")
        assert len(payload) <= limit
        return FetchResult(payload, None)


def definition_bytes() -> bytes:
    source = Path(__file__).parents[3] / "boneio" / "modbus" / "devices" / "energy_meters" / "sdm120.json"
    data = json.loads(source.read_text())
    data["model"] = "Example meter"
    return json.dumps(data).encode()


def configured_service(tmp_path: Path) -> tuple[AddonService, str]:
    config = tmp_path / "config.yaml"
    config.write_text("boneio:\n  name: test\n", encoding="utf-8")
    service = AddonService(config, token_secret=b"x" * 32)
    repository = Repository(
        id="custom-test",
        name="Test",
        url="https://example.com/index.json",
        trust=RepositoryTrust.CUSTOM,
    )
    service.storage.write_repositories(RepositoryState(repositories=[repository]))
    device = definition_bytes()
    manifest_dict = {
        "schema_version": 1,
        "id": "community.example-meter",
        "name": "Example meter",
        "version": "1.0.0",
        "type": "modbus_device_pack",
        "blackbone": {"version": ">=0.1.0,<1.0.0"},
        "author": {"name": "Maintainer"},
        "license": "MIT",
        "files": [{"path": "modbus_devices/example-meter.json", "sha256": hashlib.sha256(device).hexdigest()}],
    }
    manifest = yaml.safe_dump(manifest_dict, sort_keys=False).encode()
    release = IndexAddon(
        id="community.example-meter",
        name="Example meter",
        version="1.0.0",
        type="modbus_device_pack",
        blackbone={"version": ">=0.1.0,<1.0.0"},
        manifest_url="packs/example/addon.yaml",
        manifest_sha256=hashlib.sha256(manifest).hexdigest(),
    )
    service.registry._indexes = {"custom-test": RepositoryIndex(schema_version=1, addons=[release])}
    fake = FakeFetcher(
        {
            "https://example.com/packs/example/addon.yaml": manifest,
            "https://example.com/packs/example/modbus_devices/example-meter.json": device,
        }
    )
    service.fetcher = fake  # type: ignore[assignment]
    service.packages.fetcher = fake  # type: ignore[assignment]
    return service, release.id


@pytest.mark.asyncio
async def test_install_is_private_and_updates_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, addon_id = configured_service(tmp_path)

    async def successful_reload() -> None:
        service._sync_registry()

    monkeypatch.setattr(service, "_reload_and_validate", successful_reload)
    preview = await service.preview(addon_id, "custom-test", "1.0.0", "install")
    record, operation = service.queue_confirmed(
        addon_id,
        str(preview["confirmation_token"]),
        OperationType.INSTALL,
    )
    await operation

    completed = service.operations.get(record.id)
    assert completed.stage == OperationStage.SUCCEEDED
    assert service.storage.read_state().installed[addon_id].version == "1.0.0"
    installed = service.paths.installed_file(addon_id, "1.0.0", "modbus_devices/example-meter.json")
    assert installed.is_file()
    assert not (tmp_path / "modbus_devices" / addon_id).exists()
    assert (
        next(
            ref
            for ref in __import__("boneio.modbus.device_registry", fromlist=["list_models"]).list_models()
            if ref.key == "example-meter"
        ).source
        == f"addon:{addon_id}"
    )


@pytest.mark.asyncio
async def test_reload_failure_restores_exact_previous_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, addon_id = configured_service(tmp_path)

    async def failed_reload() -> None:
        raise AddonError("reload_failed", "Reload failed")

    monkeypatch.setattr(service, "_reload_and_validate", failed_reload)
    preview = await service.preview(addon_id, "custom-test", "1.0.0", "install")
    record, operation = service.queue_confirmed(addon_id, str(preview["confirmation_token"]), OperationType.INSTALL)
    await operation

    assert service.operations.get(record.id).stage == OperationStage.FAILED
    assert addon_id not in service.storage.read_state().installed
    assert not (service.paths.installed / addon_id).exists()


@pytest.mark.asyncio
async def test_explicit_rollback_restores_files_and_records_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, addon_id = configured_service(tmp_path)

    async def successful_reload() -> None:
        service._sync_registry()

    monkeypatch.setattr(service, "_reload_and_validate", successful_reload)
    preview = await service.preview(addon_id, "custom-test", "1.0.0", "install")
    _, install = service.queue_confirmed(addon_id, str(preview["confirmation_token"]), OperationType.INSTALL)
    await install

    installed = service.storage.read_state().installed[addon_id]
    snapshot_record = service.operations.create(
        OperationType.DISABLE,
        addon_id,
        version=installed.version,
        repository_id=installed.repository_id,
    )
    snapshot_id = service.snapshots.create(snapshot_record.id, addon_id)
    state = service.storage.read_state()
    changed = dict(state.installed)
    changed[addon_id] = installed.model_copy(update={"enabled": False})
    service.storage.write_state(state.model_copy(update={"installed": changed}))

    rollback_record, rollback = service.queue_rollback(addon_id, snapshot_id)
    await rollback

    restored = service.storage.read_state().installed[addon_id]
    assert restored.enabled is True
    assert restored.last_operation_id == rollback_record.id
    assert service.operations.get(rollback_record.id).stage == OperationStage.SUCCEEDED
