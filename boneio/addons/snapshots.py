"""Local rollback snapshots for add-on mutations."""

from __future__ import annotations

import io
import json
import os
import shutil
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from boneio.addons.errors import AddonError
from boneio.addons.models import InstalledState, validate_addon_id
from boneio.addons.paths import AddonPaths
from boneio.addons.storage import AddonStorage, fsync_directory


class SnapshotStore:
    def __init__(self, paths: AddonPaths, storage: AddonStorage, *, retention: int = 10) -> None:
        self.paths = paths
        self.storage = storage
        self.retention = retention

    def create(self, operation_id: str, addon_id: str) -> str:
        validate_addon_id(addon_id)
        destination = self.paths.snapshots / f"{operation_id}.tar.gz"
        descriptor, temporary_name = tempfile.mkstemp(prefix=".snapshot-", dir=self.paths.snapshots)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            state = self.storage.read_state()
            state_bytes = json.dumps(state.model_dump(mode="json"), sort_keys=True).encode()
            with tarfile.open(temporary, "w:gz", format=tarfile.PAX_FORMAT) as archive:
                info = tarfile.TarInfo("state.json")
                info.size = len(state_bytes)
                info.mode = 0o600
                archive.addfile(info, io.BytesIO(state_bytes))
                addon_root = self.paths.installed / addon_id
                if addon_root.is_dir():
                    for source in sorted(addon_root.rglob("*")):
                        if source.is_symlink() or not (source.is_dir() or source.is_file()):
                            raise AddonError("unsafe_installed_file", "Installed add-on contains an unsafe file type.")
                        relative = source.relative_to(addon_root)
                        archive.add(
                            source, arcname=str(PurePosixPath("installed", addon_id, *relative.parts)), recursive=False
                        )
            with temporary.open("rb") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
            fsync_directory(destination.parent)
            self._prune(addon_id)
            return destination.name
        finally:
            temporary.unlink(missing_ok=True)

    def restore(self, snapshot_name: str, addon_id: str) -> InstalledState:
        validate_addon_id(addon_id)
        if Path(snapshot_name).name != snapshot_name or not snapshot_name.endswith(".tar.gz"):
            raise AddonError("snapshot_not_found", "Snapshot was not found.", status_code=404)
        source = self.paths.snapshots / snapshot_name
        if not source.is_file():
            raise AddonError("snapshot_not_found", "Snapshot was not found.", status_code=404)
        state: InstalledState | None = None
        extracted: list[tuple[Path, bytes, int]] = []
        expected_prefix = PurePosixPath("installed", addon_id)
        try:
            with tarfile.open(source, "r:gz") as archive:
                for member in archive.getmembers():
                    name = PurePosixPath(member.name)
                    if member.issym() or member.islnk() or member.isdev():
                        raise AddonError("invalid_snapshot", "Snapshot contains an unsafe file type.")
                    if name == PurePosixPath("state.json"):
                        extracted_file = archive.extractfile(member)
                        if extracted_file is None or member.size > 2 * 1024 * 1024:
                            raise AddonError("invalid_snapshot", "Snapshot state is invalid.")
                        state = InstalledState.model_validate_json(extracted_file.read())
                        continue
                    if not name.is_relative_to(expected_prefix) or any(part in {"", ".", ".."} for part in name.parts):
                        raise AddonError("invalid_snapshot", "Snapshot contains an invalid path.")
                    if member.isdir():
                        continue
                    if not member.isfile() or member.size > 2 * 1024 * 1024:
                        raise AddonError("invalid_snapshot", "Snapshot contains an invalid file.")
                    extracted_file = archive.extractfile(member)
                    if extracted_file is None:
                        raise AddonError("invalid_snapshot", "Snapshot file could not be read.")
                    relative = Path(*name.parts[2:])
                    extracted.append((relative, extracted_file.read(), member.mode))
        except (tarfile.TarError, OSError, ValueError) as exc:
            raise AddonError("invalid_snapshot", "Snapshot could not be restored.") from exc
        if state is None:
            raise AddonError("invalid_snapshot", "Snapshot has no installed state.")

        current = self.storage.read_state()
        restored_installed = dict(current.installed)
        if addon_id in state.installed:
            restored_installed[addon_id] = state.installed[addon_id]
        else:
            restored_installed.pop(addon_id, None)
        merged = current.model_copy(update={"installed": restored_installed})

        addon_root = self.paths.installed / addon_id
        staging_root = Path(tempfile.mkdtemp(prefix=f".restore-{addon_id}-", dir=self.paths.installed))
        previous_root = Path(tempfile.mkdtemp(prefix=f".previous-{addon_id}-", dir=self.paths.installed))
        previous_root.rmdir()
        old_moved = False
        staged_moved = False
        try:
            for relative, payload, mode in extracted:
                target = staging_root / relative
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
                with target.open("wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                target.chmod(mode & 0o640)
            for directory in sorted(
                (path for path in staging_root.rglob("*") if path.is_dir()),
                key=lambda path: len(path.parts),
                reverse=True,
            ):
                fsync_directory(directory)
            fsync_directory(staging_root)

            if addon_root.exists():
                addon_root.rename(previous_root)
                old_moved = True
            if addon_id in state.installed:
                staging_root.rename(addon_root)
                staged_moved = True
            fsync_directory(self.paths.installed)
            self.storage.write_state(merged)
            if old_moved:
                shutil.rmtree(previous_root)
            if not staged_moved:
                shutil.rmtree(staging_root)
            fsync_directory(self.paths.installed)
        except Exception:
            if staged_moved and addon_root.exists():
                shutil.rmtree(addon_root)
            if old_moved and previous_root.exists():
                previous_root.rename(addon_root)
            shutil.rmtree(staging_root, ignore_errors=True)
            fsync_directory(self.paths.installed)
            raise
        return merged

    def list(self, addon_id: str) -> list[dict[str, object]]:
        validate_addon_id(addon_id)
        results: list[dict[str, object]] = []
        operation_addon = {record.id: record.addon_id for record in self.storage_operations()}
        for path in sorted(self.paths.snapshots.glob("*.tar.gz"), key=lambda item: item.stat().st_mtime, reverse=True):
            operation_id = path.name.removesuffix(".tar.gz")
            if operation_addon.get(operation_id) == addon_id:
                results.append(
                    {
                        "id": path.name,
                        "operation_id": operation_id,
                        "created_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
                    }
                )
        return results

    def storage_operations(self):
        from boneio.addons.operations import OperationStore

        return OperationStore(self.paths).list()

    def _prune(self, addon_id: str) -> None:
        snapshots = self.list(addon_id)
        installed = self.storage.read_state().installed.get(addon_id)
        protected_operations = {installed.last_operation_id} if installed else set()
        removable = [item for item in snapshots if item["operation_id"] not in protected_operations]
        keep_unprotected = max(0, self.retention - len(protected_operations))
        for item in removable[keep_unprotected:]:
            (self.paths.snapshots / str(item["id"])).unlink(missing_ok=True)
            from boneio.addons.operations import OperationStore

            operations = OperationStore(self.paths)
            record = operations.get(str(item["operation_id"]))
            operations.save(record.model_copy(update={"snapshot_path": None}))
