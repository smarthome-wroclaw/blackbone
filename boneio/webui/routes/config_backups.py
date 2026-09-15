"""Configuration backups routes for BoneIO Web UI."""

from __future__ import annotations

import contextlib
import io
import logging
import tarfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from fastapi import Body, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from boneio.core.config.yaml_util import (
    load_config_from_file,
    load_yaml_file,
    update_config_section,
)
from boneio.core.manager import Manager
from boneio.version import __version__
from boneio.webui.routes.config_core import (
    _get_app_state,
    invalidate_config_cache,
    router,
)

_LOGGER = logging.getLogger(__name__)

MAX_BACKUPS = 10
_MAX_RESTORE_FILE = 2 * 1024 * 1024
_MAX_RESTORE_MEMBERS = 2048


def _iter_config_backup_files(config_dir: Path):
    """Yield durable configuration files, including pinned declarative add-ons."""
    seen: set[Path] = set()
    for pattern in ("*.yaml", "*.yml"):
        for path in config_dir.glob(pattern):
            if path.is_file() and not path.is_symlink():
                seen.add(path)
                yield path, path.name
    for subdir in config_dir.iterdir():
        if not subdir.is_dir() or subdir.name.startswith(".") or subdir.name in {"backups", "addons"}:
            continue
        patterns = ("*.yaml", "*.yml", "*.json") if subdir.name == "modbus_devices" else ("*.yaml", "*.yml")
        for pattern in patterns:
            for path in subdir.glob(pattern):
                if path.is_file() and not path.is_symlink() and path not in seen:
                    seen.add(path)
                    yield path, f"{subdir.name}/{path.name}"

    addons = config_dir / "addons"
    for name in ("repositories.json", "state.json"):
        path = addons / name
        if path.is_file() and not path.is_symlink():
            yield path, f"addons/{name}"
    installed = addons / "installed"
    if installed.is_dir():
        for path in installed.rglob("*"):
            relative = path.relative_to(addons)
            allowed = (len(relative.parts) == 4 and relative.parts[0] == "installed" and path.name == "manifest.yaml") or (
                len(relative.parts) == 6
                and relative.parts[0] == "installed"
                and relative.parts[3:5] == ("files", "modbus_devices")
                and path.suffix == ".json"
            )
            if allowed and path.is_file() and not path.is_symlink():
                yield path, f"addons/{relative.as_posix()}"


def _add_config_files_to_tar(archive: tarfile.TarFile, config_dir: Path) -> None:
    for source, archive_name in _iter_config_backup_files(config_dir):
        archive.add(source, arcname=archive_name, recursive=False)
        _LOGGER.debug("Added %s to config archive", archive_name)


def _allowed_restore_path(name: str) -> bool:
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return False
    if len(path.parts) <= 2 and path.suffix in {".yaml", ".yml"}:
        return True
    if len(path.parts) == 2 and path.parts[0] == "modbus_devices" and path.suffix == ".json":
        return True
    if name in {"addons/repositories.json", "addons/state.json"}:
        return True
    if len(path.parts) >= 5 and path.parts[0] == "addons" and path.parts[1] == "installed":
        if path.name == "manifest.yaml" and len(path.parts) == 5:
            return True
        return len(path.parts) == 7 and path.parts[4:6] == ("files", "modbus_devices") and path.suffix == ".json"
    return False


def _restore_config_members(archive: tarfile.TarFile, config_dir: Path) -> list[str]:
    from boneio.addons.storage import atomic_write_bytes

    restored: list[str] = []
    members = archive.getmembers()
    if len(members) > _MAX_RESTORE_MEMBERS:
        raise ValueError("Archive contains too many files")
    seen: set[str] = set()
    for member in members:
        if member.name == "_boneio_meta.json":
            continue
        folded_name = member.name.casefold()
        if folded_name in seen:
            raise ValueError(f"Duplicate file path in archive: {member.name}")
        seen.add(folded_name)
        if not _allowed_restore_path(member.name):
            raise ValueError(f"Invalid file path in archive: {member.name}")
        if not member.isfile() or member.issym() or member.islnk() or member.size > _MAX_RESTORE_FILE:
            raise ValueError(f"Invalid file type or size in archive: {member.name}")
        source = archive.extractfile(member)
        if source is None:
            raise ValueError(f"Could not read archive member: {member.name}")
        payload = source.read(_MAX_RESTORE_FILE + 1)
        if len(payload) > _MAX_RESTORE_FILE:
            raise ValueError(f"Archive member is too large: {member.name}")
        target = (config_dir / member.name).resolve()
        if not target.is_relative_to(config_dir.resolve()):
            raise ValueError(f"Invalid file path in archive: {member.name}")
        atomic_write_bytes(target, payload)
        restored.append(member.name)
    return restored


def _add_backup_metadata_to_tar(tar: tarfile.TarFile, config_helper):
    import json
    import socket

    meta = {
        "effective_serial": config_helper.serial_number,
        "real_serial": config_helper.real_serial,
        "hostname": socket.gethostname(),
        "created_at": datetime.now().isoformat(),
        "version": __version__,
    }
    meta_bytes = json.dumps(meta, indent=2).encode("utf-8")

    tarinfo = tarfile.TarInfo(name="_boneio_meta.json")
    tarinfo.size = len(meta_bytes)
    tarinfo.mtime = int(datetime.now().timestamp())

    tar.addfile(tarinfo, io.BytesIO(meta_bytes))


def _apply_serial_override_from_tar(fileobj, config_file):
    import json

    with contextlib.suppress(Exception):
        fileobj.seek(0)
    effective_serial = None
    try:
        with tarfile.open(fileobj=fileobj, mode="r:gz") as tar:
            try:
                meta_member = tar.getmember("_boneio_meta.json")
                meta_file = tar.extractfile(meta_member)
                if meta_file:
                    meta = json.loads(meta_file.read().decode("utf-8"))
                    effective_serial = meta.get("effective_serial")
            except KeyError:
                pass
    except Exception as e:
        _LOGGER.warning("Could not read backup metadata for override: %s", e)

    if not effective_serial:
        _LOGGER.info("No effective_serial found in backup metadata, skipping override")
        return

    try:
        config_content = load_yaml_file(config_file)
        boneio_data = config_content.get("boneio", {})
        if not isinstance(boneio_data, dict):
            boneio_data = {}

        boneio_data["serial_override"] = effective_serial
        update_config_section(config_file, "boneio", boneio_data)
        _LOGGER.info("Successfully applied serial_override: %s", effective_serial)
    except Exception as e:
        _LOGGER.error("Failed to write serial_override to config: %s", e)


@router.get("/config/download")
async def download_config():
    """Download current configuration as a tar.gz archive."""
    config_file = _get_app_state().yaml_config_file
    config_dir = Path(config_file).parent

    buffer = io.BytesIO()

    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        _add_config_files_to_tar(tar, config_dir)

        manager: Manager = _get_app_state().manager
        _add_backup_metadata_to_tar(tar, manager.config_helper)

    buffer.seek(0)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    manager: Manager = _get_app_state().manager
    device_name = manager.config_helper.serial_number
    filename = f"{device_name}_config_{timestamp}.tar.gz"

    _LOGGER.info(f"Downloading config archive: {filename}")

    return StreamingResponse(
        buffer, media_type="application/gzip", headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/config/restore")
async def restore_config(file: UploadFile = File(...), override_serial: bool = Form(False)):
    """Restore configuration from a tar.gz archive."""
    config_file = _get_app_state().yaml_config_file
    config_dir = Path(config_file).parent

    try:
        if not file.filename or not file.filename.endswith((".tar.gz", ".tgz")):
            return {"status": "error", "message": "Invalid file type. Please upload a .tar.gz or .tgz file."}

        contents = await file.read()
        buffer = io.BytesIO(contents)

        # Create backup with version in filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = config_dir / "backups"
        backup_dir.mkdir(exist_ok=True)
        backup_path = backup_dir / f"config_backup_v{__version__}_{timestamp}.tar.gz"

        with tarfile.open(backup_path, mode="w:gz") as tar:
            _add_config_files_to_tar(tar, config_dir)
            _add_backup_metadata_to_tar(tar, _get_app_state().manager.config_helper)

        _LOGGER.info(f"Created backup before restore: {backup_path}")

        # Extract and restore
        with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
            restored_files = _restore_config_members(tar, config_dir)

        if override_serial:
            _apply_serial_override_from_tar(io.BytesIO(contents), config_file)

        invalidate_config_cache()

        # Validate
        try:
            load_config_from_file(config_file=_get_app_state().yaml_config_file)
            validation_status = "success"
            validation_message = "Configuration is valid"
        except Exception as e:
            validation_status = "warning"
            validation_message = f"Configuration restored but validation failed: {str(e)}"
            _LOGGER.warning(f"Restored config validation failed: {e}")

        return {
            "status": "success",
            "message": f"Restored {len(restored_files)} files from backup",
            "restored_files": restored_files,
            "backup_path": str(backup_path),
            "validation_status": validation_status,
            "validation_message": validation_message,
            "restart_required": True,
        }

    except tarfile.TarError as e:
        _LOGGER.error(f"Failed to extract archive: {e}")
        return {"status": "error", "message": f"Failed to extract archive: {str(e)}"}
    except Exception as e:
        _LOGGER.error(f"Failed to restore config: {e}")
        return {"status": "error", "message": f"Failed to restore configuration: {str(e)}"}


@router.get("/config/backups")
async def list_config_backups():
    """List available configuration backups from disk."""
    config_file = _get_app_state().yaml_config_file
    config_dir = Path(config_file).parent
    backup_dir = config_dir / "backups"

    if not backup_dir.exists():
        return {"backups": []}

    backups = []
    for backup_file in sorted(backup_dir.glob("config_backup_*.tar.gz"), reverse=True):
        try:
            filename_parts = backup_file.stem.replace("config_backup_", "")

            version = None
            timestamp_str = filename_parts
            if filename_parts.startswith("v"):
                parts = filename_parts.split("_", 1)
                if len(parts) == 2:
                    version = parts[0][1:]
                    timestamp_str = parts[1]

            formatted_timestamp = timestamp_str
            if len(timestamp_str) == 15 and timestamp_str[8] == "_":
                date_part = timestamp_str[:8]
                time_part = timestamp_str[9:]
                formatted_timestamp = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"

            file_count = 0
            try:
                with tarfile.open(backup_file, "r:gz") as tar:
                    file_count = len(tar.getmembers())
            except Exception:
                pass

            backups.append(
                {
                    "path": str(backup_file),
                    "filename": backup_file.name,
                    "version": version or "unknown",
                    "timestamp": formatted_timestamp,
                    "timestamp_raw": timestamp_str,
                    "size": backup_file.stat().st_size,
                    "file_count": file_count,
                }
            )
        except Exception as e:
            _LOGGER.warning(f"Error processing backup {backup_file}: {e}")
            continue

    return {"backups": backups}


@router.post("/config/restore_backup")
async def restore_config_backup(
    backup_path: str = Body(..., embed=True),
    override_serial: bool = Body(False, embed=True),
):
    """Restore configuration from a backup file on disk."""
    config_file = _get_app_state().yaml_config_file
    config_dir = Path(config_file).parent
    backup_file = Path(backup_path)

    backup_dir = config_dir / "backups"
    try:
        backup_file = backup_file.resolve()
        backup_dir = backup_dir.resolve()
        if not str(backup_file).startswith(str(backup_dir)):
            return {"status": "error", "message": "Invalid backup path"}
    except Exception:
        return {"status": "error", "message": "Invalid backup path"}

    if not backup_file.exists():
        return {"status": "error", "message": "Backup file not found"}

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_backup_path = backup_dir / f"config_backup_v{__version__}_{timestamp}.tar.gz"

        with tarfile.open(new_backup_path, mode="w:gz") as tar:
            _add_config_files_to_tar(tar, config_dir)
            _add_backup_metadata_to_tar(tar, _get_app_state().manager.config_helper)

        _LOGGER.info(f"Created backup before restore: {new_backup_path}")

        with tarfile.open(backup_file, mode="r:gz") as tar:
            restored_files = _restore_config_members(tar, config_dir)

        if override_serial:
            with open(backup_file, "rb") as f:
                _apply_serial_override_from_tar(f, config_file)

        invalidate_config_cache()

        try:
            load_config_from_file(config_file=_get_app_state().yaml_config_file)
            validation_status = "success"
            validation_message = "Configuration is valid"
        except Exception as e:
            validation_status = "warning"
            validation_message = f"Configuration restored but validation failed: {str(e)}"
            _LOGGER.warning(f"Restored config validation failed: {e}")

        return {
            "status": "success",
            "message": f"Restored {len(restored_files)} files from backup",
            "restored_files": restored_files,
            "backup_created": str(new_backup_path),
            "validation_status": validation_status,
            "validation_message": validation_message,
            "restart_required": True,
        }

    except tarfile.TarError as e:
        _LOGGER.error(f"Failed to extract backup: {e}")
        return {"status": "error", "message": f"Failed to extract backup: {str(e)}"}
    except Exception as e:
        _LOGGER.error(f"Failed to restore backup: {e}")
        return {"status": "error", "message": f"Failed to restore backup: {str(e)}"}


@router.post("/config/create_backup")
async def create_config_backup():
    """Create a configuration backup on disk with version in filename."""
    config_file = _get_app_state().yaml_config_file
    config_dir = Path(config_file).parent

    try:
        backup_dir = config_dir / "backups"
        backup_dir.mkdir(exist_ok=True)

        all_backups = sorted(backup_dir.glob("config_backup_*.tar.gz"), reverse=True)
        _LOGGER.debug(f"Found {len(all_backups)} existing backups, max allowed: {MAX_BACKUPS}")

        if len(all_backups) >= MAX_BACKUPS:
            backups_to_remove = all_backups[MAX_BACKUPS - 1 :]
            _LOGGER.info(f"Removing {len(backups_to_remove)} old backups to maintain limit of {MAX_BACKUPS}")
            for old_backup in backups_to_remove:
                try:
                    old_backup.unlink()
                    _LOGGER.info(f"Removed old backup: {old_backup.name}")
                except Exception as e:
                    _LOGGER.warning(f"Failed to remove old backup {old_backup.name}: {e}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"config_backup_v{__version__}_{timestamp}.tar.gz"

        with tarfile.open(backup_path, mode="w:gz") as tar:
            _add_config_files_to_tar(tar, config_dir)
            _add_backup_metadata_to_tar(tar, _get_app_state().manager.config_helper)

        _LOGGER.info(f"Created config backup: {backup_path}")

        final_count = len(list(backup_dir.glob("config_backup_*.tar.gz")))
        _LOGGER.debug(f"Total backups after creation: {final_count}")

        file_count = 0
        with tarfile.open(backup_path, "r:gz") as tar:
            file_count = len(tar.getmembers())

        return {
            "status": "success",
            "message": f"Backup created with {file_count} files",
            "backup_path": str(backup_path),
            "filename": backup_path.name,
            "version": __version__,
            "file_count": file_count,
        }

    except Exception as e:
        _LOGGER.error(f"Failed to create backup: {e}")
        return {"status": "error", "message": f"Failed to create backup: {str(e)}"}


@router.get("/config/download_backup")
async def download_config_backup(backup_path: str):
    """Download a specific configuration backup from disk."""
    config_file = _get_app_state().yaml_config_file
    config_dir = Path(config_file).parent
    backup_file = Path(backup_path)

    backup_dir = config_dir / "backups"
    try:
        backup_file = backup_file.resolve()
        backup_dir = backup_dir.resolve()
        if not str(backup_file).startswith(str(backup_dir)):
            raise HTTPException(status_code=403, detail="Invalid backup path")
    except Exception as e:
        raise HTTPException(status_code=403, detail="Invalid backup path") from e

    if not backup_file.exists():
        raise HTTPException(status_code=404, detail="Backup file not found")

    _LOGGER.info(f"Downloading backup: {backup_file.name}")

    return StreamingResponse(
        open(backup_file, "rb"),
        media_type="application/gzip",
        headers={"Content-Disposition": f"attachment; filename={backup_file.name}"},
    )


@router.delete("/config/delete_backup")
async def delete_config_backup(backup_path: str = Body(..., embed=True)):
    """Delete a specific configuration backup from disk."""
    config_file = _get_app_state().yaml_config_file
    config_dir = Path(config_file).parent
    backup_file = Path(backup_path)

    backup_dir = config_dir / "backups"
    try:
        backup_file = backup_file.resolve()
        backup_dir = backup_dir.resolve()
        if not str(backup_file).startswith(str(backup_dir)):
            return {"status": "error", "message": "Invalid backup path"}
    except Exception:
        return {"status": "error", "message": "Invalid backup path"}

    if not backup_file.exists():
        return {"status": "error", "message": "Backup file not found"}

    try:
        backup_file.unlink()
        _LOGGER.info(f"Deleted backup: {backup_file.name}")

        return {"status": "success", "message": f"Backup {backup_file.name} deleted successfully"}
    except Exception as e:
        _LOGGER.error(f"Failed to delete backup: {e}")
        return {"status": "error", "message": f"Failed to delete backup: {str(e)}"}


@router.post("/config/inspect_backup_file")
async def inspect_backup_file(file: UploadFile = File(...)):
    """Inspect uploaded backup file to extract metadata."""
    try:
        contents = await file.read()
        fileobj = io.BytesIO(contents)
        config_helper = _get_app_state().manager.config_helper
        return _inspect_tar_fileobj(fileobj, config_helper)
    except Exception as e:
        _LOGGER.error("Failed to inspect backup file: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/config/inspect_backup_path")
async def inspect_backup_path(backup_path: str = Body(..., embed=True)):
    """Inspect backup file on disk to extract metadata."""
    try:
        config_file = _get_app_state().yaml_config_file
        config_dir = Path(config_file).parent
        backup_file = Path(backup_path)

        backup_dir = config_dir / "backups"
        backup_file = backup_file.resolve()
        backup_dir = backup_dir.resolve()
        if not str(backup_file).startswith(str(backup_dir)):
            raise HTTPException(status_code=400, detail="Invalid backup path")

        if not backup_file.exists():
            raise HTTPException(status_code=404, detail="Backup file not found")

        config_helper = _get_app_state().manager.config_helper
        with open(backup_file, "rb") as f:
            return _inspect_tar_fileobj(f, config_helper)
    except HTTPException:
        raise
    except Exception as e:
        _LOGGER.error("Failed to inspect backup path: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


def _inspect_tar_fileobj(fileobj, config_helper):
    import json

    meta = None
    try:
        with contextlib.suppress(Exception):
            fileobj.seek(0)
        with tarfile.open(fileobj=fileobj, mode="r:gz") as tar:
            try:
                meta_member = tar.getmember("_boneio_meta.json")
                meta_file = tar.extractfile(meta_member)
                if meta_file:
                    meta = json.loads(meta_file.read().decode("utf-8"))
            except KeyError:
                pass
    except Exception as e:
        _LOGGER.warning("Failed to extract backup metadata: %s", e)

    current_serial = config_helper.serial_number
    mismatch = False
    if meta and "effective_serial" in meta:
        mismatch = meta["effective_serial"] != current_serial

    return {
        "backup_meta": meta,
        "current_serial": current_serial,
        "serial_mismatch": mismatch,
    }
