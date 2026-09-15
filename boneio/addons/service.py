"""Transactional lifecycle service for declarative add-ons."""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from boneio.addons.errors import AddonError
from boneio.addons.models import (
    InstalledAddon,
    OperationRecord,
    OperationStage,
    OperationType,
    RepositoryCreateRequest,
)
from boneio.addons.network import SafeFetcher
from boneio.addons.operations import FINAL_STAGES, OperationStore
from boneio.addons.package import PackageValidator
from boneio.addons.paths import AddonPaths
from boneio.addons.registry import RegistryClient
from boneio.addons.snapshots import SnapshotStore
from boneio.addons.storage import AddonStorage, fsync_directory
from boneio.addons.validation import AddonValidator
from boneio.modbus import device_registry

_LOGGER = logging.getLogger(__name__)


class AddonService:
    """Owns all add-on state transitions; routes only adapt HTTP input/output."""

    def __init__(
        self, config_file: str | Path, *, manager: object | None = None, token_secret: bytes | None = None
    ) -> None:
        self.config_file = Path(config_file).resolve()
        self.paths = AddonPaths.from_config_file(self.config_file)
        self.storage = AddonStorage(self.paths)
        self.operations = OperationStore(self.paths)
        self.snapshots = SnapshotStore(self.paths, self.storage)
        self.fetcher = SafeFetcher()
        self.registry = RegistryClient(self.paths, self.storage, self.fetcher)
        self.packages = PackageValidator(self.paths, self.fetcher)
        self.validator = AddonValidator(
            self.storage,
            self.registry,
            self.packages,
            secret=token_secret,
        )
        self.manager = manager
        self.recovery_error: str | None = None
        self._last_refresh = 0.0
        self._recover_interrupted()
        self._sync_registry()

    def _recover_interrupted(self) -> None:
        for record in self.operations.list():
            if record.stage in FINAL_STAGES:
                continue
            try:
                if record.stage in {
                    OperationStage.APPLYING,
                    OperationStage.RELOADING,
                    OperationStage.ROLLING_BACK,
                }:
                    if not record.snapshot_path:
                        raise AddonError("recovery_failed", "Interrupted mutation has no recovery snapshot.")
                    self.snapshots.restore(record.snapshot_path, record.addon_id)
                self.operations.update(
                    record,
                    OperationStage.INTERRUPTED,
                    "Operation was interrupted; its previous state was restored.",
                )
            except Exception:
                _LOGGER.exception("Could not recover interrupted add-on operation %s", record.id)
                self.recovery_error = "An interrupted add-on operation requires manual recovery."

    def _ensure_recovered(self) -> None:
        if self.recovery_error:
            raise AddonError("recovery_required", self.recovery_error, status_code=503)

    def state(self) -> dict[str, object]:
        repository_state = self.storage.read_repositories()
        installed_state = self.storage.read_state()
        return {
            "health": "recovery_required" if self.recovery_error else "ok",
            "repositories": [
                {
                    **item.model_dump(mode="json"),
                    "offline": self.registry._offline.get(item.id, False),
                }
                for item in repository_state.repositories
            ],
            "installed": {
                addon_id: item.model_dump(mode="json") for addon_id, item in installed_state.installed.items()
            },
            "updates": [
                item["id"]
                for item in self.registry.catalog()["addons"]
                if isinstance(item, dict) and item.get("update_available")
            ],
        }

    async def add_repository(self, request: RepositoryCreateRequest):
        self._ensure_recovered()
        with self.storage.mutation_lock:
            return await self.registry.add_repository(request.name, str(request.url))

    async def refresh(self) -> dict[str, object]:
        self._ensure_recovered()
        now = time.monotonic()
        if now - self._last_refresh < 10:
            raise AddonError("refresh_limited", "Repositories were refreshed recently.", status_code=429)
        with self.storage.mutation_lock:
            result = await self.registry.refresh()
            self._last_refresh = time.monotonic()
            return result

    def remove_repository(self, repository_id: str) -> None:
        self._ensure_recovered()
        with self.storage.mutation_lock:
            self.registry.remove_repository(repository_id)

    async def preview(self, addon_id: str, repository_id: str, version: str, action: str) -> dict[str, object]:
        self._ensure_recovered()
        if action not in {"install", "update", "downgrade"}:
            raise AddonError("invalid_action", "Unsupported preview action.")
        return await self.validator.preview(addon_id, repository_id, version, action)  # type: ignore[arg-type]

    def queue_confirmed(
        self,
        addon_id: str,
        confirmation_token: str,
        operation_type: OperationType,
    ) -> tuple[OperationRecord, Coroutine[Any, Any, None]]:
        self._ensure_recovered()
        allowed = {"install"} if operation_type == OperationType.INSTALL else {"update", "downgrade"}
        binding = self.validator.verify(confirmation_token, addon_id, allowed)
        self.storage.mutation_lock.acquire()
        try:
            record = self.operations.create(
                operation_type,
                addon_id,
                version=binding.version,
                repository_id=binding.repository_id,
            )
        except Exception:
            self.storage.mutation_lock.release()
            raise
        return record, self._run_confirmed(record, confirmation_token)

    async def _run_confirmed(self, record: OperationRecord, token: str) -> None:
        snapshot_name: str | None = None
        staged_root: Path | None = None
        try:
            binding = self.validator.verify(token, record.addon_id, {"install", "update", "downgrade"})
            record = self.operations.update(record, OperationStage.DOWNLOADING, "Downloading the reviewed release.")
            repository = self.registry.repository(binding.repository_id)
            release = self.registry.exact_release(binding.repository_id, binding.addon_id, binding.version)
            if release.manifest_sha256 != binding.manifest_sha256:
                raise AddonError(
                    "manifest_changed", "Repository changed since the preview; review it again.", status_code=409
                )
            package = await self.packages.stage(record.id, repository, release)
            staged_root = package.root
            record = self.operations.update(
                record, OperationStage.VALIDATING, "Validating package files and ownership."
            )
            conflicts = self.validator.conflicts(package, replacing_addon=record.addon_id)
            if conflicts:
                raise AddonError(
                    "model_conflict",
                    f"Model '{conflicts[0]['model']}' is already provided by another source.",
                    details=conflicts[0],
                    status_code=409,
                )

            snapshot_name = self.snapshots.create(record.id, record.addon_id)
            record = self.operations.update(
                record,
                OperationStage.APPLYING,
                "Applying the validated package.",
                snapshot_path=snapshot_name,
            )
            destination = self.paths.install_dir(record.addon_id, binding.version)
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
            if destination.exists():
                shutil.rmtree(destination)
            package.root.rename(destination)
            fsync_directory(destination.parent)
            staged_root = None

            state = self.storage.read_state()
            previous = state.installed.get(record.addon_id)
            installed = dict(state.installed)
            installed[record.addon_id] = InstalledAddon(
                version=binding.version,
                repository_id=binding.repository_id,
                manifest_sha256=binding.manifest_sha256,
                enabled=True,
                installed_at=datetime.now(UTC),
                files=[item.path for item in package.manifest.files],
                last_operation_id=record.id,
            )
            self.storage.write_state(state.model_copy(update={"installed": installed}))

            record = self.operations.update(record, OperationStage.RELOADING, "Reloading Modbus definitions.")
            await self._reload_and_validate()
            if previous and previous.version != binding.version:
                shutil.rmtree(self.paths.install_dir(record.addon_id, previous.version), ignore_errors=True)
            self.validator.consume(token)
            self.operations.update(
                record,
                OperationStage.SUCCEEDED,
                "Add-on installed successfully.",
                reload_required=True,
            )
        except Exception as exc:
            await self._fail_and_restore(record, exc, snapshot_name)
        finally:
            if staged_root:
                shutil.rmtree(staged_root, ignore_errors=True)
            self.storage.mutation_lock.release()

    def queue_toggle(self, addon_id: str, *, enabled: bool) -> tuple[OperationRecord, Coroutine[Any, Any, None]]:
        self._ensure_recovered()
        state = self.storage.read_state()
        installed = state.installed.get(addon_id)
        if installed is None:
            raise AddonError("not_installed", "Add-on is not installed.", status_code=404)
        if installed.enabled == enabled:
            raise AddonError(
                "already_enabled" if enabled else "already_disabled",
                "Add-on is already in that state.",
                status_code=409,
            )
        if not enabled:
            self._ensure_not_referenced(addon_id, installed)
        self.storage.mutation_lock.acquire()
        operation_type = OperationType.ENABLE if enabled else OperationType.DISABLE
        try:
            record = self.operations.create(
                operation_type, addon_id, version=installed.version, repository_id=installed.repository_id
            )
        except Exception:
            self.storage.mutation_lock.release()
            raise
        return record, self._run_toggle(record, enabled)

    async def _run_toggle(self, record: OperationRecord, enabled: bool) -> None:
        snapshot_name: str | None = None
        try:
            snapshot_name = self.snapshots.create(record.id, record.addon_id)
            record = self.operations.update(
                record, OperationStage.APPLYING, "Updating add-on state.", snapshot_path=snapshot_name
            )
            state = self.storage.read_state()
            current = state.installed[record.addon_id]
            installed = dict(state.installed)
            installed[record.addon_id] = current.model_copy(update={"enabled": enabled, "last_operation_id": record.id})
            self.storage.write_state(state.model_copy(update={"installed": installed}))
            record = self.operations.update(record, OperationStage.RELOADING, "Reloading Modbus definitions.")
            await self._reload_and_validate()
            self.operations.update(
                record, OperationStage.SUCCEEDED, "Add-on state changed successfully.", reload_required=True
            )
        except Exception as exc:
            await self._fail_and_restore(record, exc, snapshot_name)
        finally:
            self.storage.mutation_lock.release()

    def queue_remove(self, addon_id: str) -> tuple[OperationRecord, Coroutine[Any, Any, None]]:
        self._ensure_recovered()
        state = self.storage.read_state()
        installed = state.installed.get(addon_id)
        if installed is None:
            raise AddonError("not_installed", "Add-on is not installed.", status_code=404)
        self._ensure_not_referenced(addon_id, installed)
        self.storage.mutation_lock.acquire()
        try:
            record = self.operations.create(
                OperationType.REMOVE, addon_id, version=installed.version, repository_id=installed.repository_id
            )
        except Exception:
            self.storage.mutation_lock.release()
            raise
        return record, self._run_remove(record)

    async def _run_remove(self, record: OperationRecord) -> None:
        snapshot_name: str | None = None
        try:
            snapshot_name = self.snapshots.create(record.id, record.addon_id)
            record = self.operations.update(
                record, OperationStage.APPLYING, "Removing add-on-owned files.", snapshot_path=snapshot_name
            )
            state = self.storage.read_state()
            installed = dict(state.installed)
            installed.pop(record.addon_id, None)
            self.storage.write_state(state.model_copy(update={"installed": installed}))
            record = self.operations.update(record, OperationStage.RELOADING, "Reloading Modbus definitions.")
            await self._reload_and_validate()
            shutil.rmtree(self.paths.installed / record.addon_id, ignore_errors=True)
            self.operations.update(
                record, OperationStage.SUCCEEDED, "Add-on removed successfully.", reload_required=True
            )
        except Exception as exc:
            await self._fail_and_restore(record, exc, snapshot_name)
        finally:
            self.storage.mutation_lock.release()

    def queue_rollback(self, addon_id: str, snapshot_id: str) -> tuple[OperationRecord, Coroutine[Any, Any, None]]:
        self._ensure_recovered()
        if not any(item["id"] == snapshot_id for item in self.snapshots.list(addon_id)):
            raise AddonError("snapshot_not_found", "Snapshot was not found.", status_code=404)
        current = self.storage.read_state().installed.get(addon_id)
        self.storage.mutation_lock.acquire()
        try:
            record = self.operations.create(
                OperationType.ROLLBACK,
                addon_id,
                version=current.version if current else None,
                repository_id=current.repository_id if current else None,
            )
        except Exception:
            self.storage.mutation_lock.release()
            raise
        return record, self._run_rollback(record, snapshot_id)

    async def _run_rollback(self, record: OperationRecord, target_snapshot: str) -> None:
        recovery_snapshot: str | None = None
        try:
            recovery_snapshot = self.snapshots.create(record.id, record.addon_id)
            record = self.operations.update(
                record, OperationStage.APPLYING, "Restoring rollback point.", snapshot_path=recovery_snapshot
            )
            restored_state = self.snapshots.restore(target_snapshot, record.addon_id)
            restored_addon = restored_state.installed.get(record.addon_id)
            if restored_addon is not None:
                installed = dict(restored_state.installed)
                installed[record.addon_id] = restored_addon.model_copy(update={"last_operation_id": record.id})
                self.storage.write_state(restored_state.model_copy(update={"installed": installed}))
            record = self.operations.update(
                record,
                OperationStage.RELOADING,
                "Reloading restored definitions.",
                version=restored_addon.version if restored_addon else record.version,
                repository_id=restored_addon.repository_id if restored_addon else record.repository_id,
            )
            await self._reload_and_validate()
            self.operations.update(
                record, OperationStage.SUCCEEDED, "Rollback completed successfully.", reload_required=True
            )
        except Exception as exc:
            await self._fail_and_restore(record, exc, recovery_snapshot)
        finally:
            self.storage.mutation_lock.release()

    async def _fail_and_restore(self, record: OperationRecord, exc: Exception, snapshot_name: str | None) -> None:
        error = exc if isinstance(exc, AddonError) else AddonError("operation_failed", "Add-on operation failed.")
        if snapshot_name:
            try:
                record = self.operations.update(record, OperationStage.ROLLING_BACK, "Restoring the previous state.")
                self.snapshots.restore(snapshot_name, record.addon_id)
                await self._reload_and_validate()
            except Exception:
                _LOGGER.exception("Rollback failed for add-on operation %s", record.id)
                error = AddonError("rollback_failed", "Operation failed and automatic rollback could not be completed.")
                self.recovery_error = error.message
        self.operations.update(
            record,
            OperationStage.FAILED,
            error.message,
            validation_errors=[{"code": error.code, "message": error.message}],
        )

    def _sync_registry(self) -> None:
        device_registry.configure_from_config(str(self.config_file))
        device_registry.invalidate()

    async def _reload_and_validate(self) -> None:
        self._sync_registry()
        from boneio.core.config.yaml_util import clear_config_cache, load_config_from_file

        clear_config_cache(clear_static=True)
        await asyncio.to_thread(load_config_from_file, str(self.config_file))
        if self.manager is not None and hasattr(self.manager, "reload_config"):
            result = await self.manager.reload_config(reload_sections=["modbus_devices"])
            if result.get("status") != "success":
                raise AddonError("reload_failed", "Modbus devices could not be reloaded.")

    def _ensure_not_referenced(self, addon_id: str, installed: InstalledAddon) -> None:
        supplied = {Path(path).stem for path in installed.files}
        config: dict[str, object] = {}
        try:
            if self.manager is not None and hasattr(self.manager, "config_helper"):
                config = self.manager.config_helper.get_config()
            else:
                from boneio.core.config.yaml_util import load_yaml_file

                config = load_yaml_file(str(self.config_file)) or {}
        except Exception as exc:
            raise AddonError(
                "configuration_unavailable", "Active configuration could not be checked.", status_code=503
            ) from exc
        references = [
            str(item.get("id") or item.get("name") or item.get("model"))
            for item in config.get("modbus_devices", [])  # type: ignore[union-attr]
            if isinstance(item, dict) and item.get("model") in supplied
        ]
        if references:
            raise AddonError(
                "addon_in_use",
                "An active Modbus device uses a model from this add-on.",
                details={"devices": references, "addon_id": addon_id},
                status_code=409,
            )
