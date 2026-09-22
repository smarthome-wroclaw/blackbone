from __future__ import annotations

import io
import sys
import tarfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("gpiod", MagicMock())
sys.modules.setdefault("gpiod.line", MagicMock())
sys.modules.setdefault("smbus2", MagicMock())

from boneio.webui.routes.config_backups import (  # noqa: E402
    _add_config_files_to_tar,
    _restore_config_members,
)


def test_backup_restores_pinned_addon_without_transient_files(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    device = source / "addons/installed/community.example/1.0.0/files/modbus_devices/example.json"
    manifest = source / "addons/installed/community.example/1.0.0/manifest.yaml"
    for path, content in (
        (source / "config.yaml", "boneio: {}\n"),
        (source / "addons/state.json", '{"schema_version": 1, "installed": {}}\n'),
        (source / "addons/repositories.json", '{"schema_version": 1, "repositories": []}\n'),
        (manifest, "schema_version: 1\n"),
        (device, '{"model": "example"}\n'),
        (source / "addons/cache/index.json", "transient"),
        (source / "addons/operations/operation.json", "transient"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        _add_config_files_to_tar(archive, source)
    buffer.seek(0)
    with tarfile.open(fileobj=buffer, mode="r:gz") as archive:
        restored = _restore_config_members(archive, destination)

    assert "addons/state.json" in restored
    assert "addons/installed/community.example/1.0.0/manifest.yaml" in restored
    assert (destination / device.relative_to(source)).read_text(encoding="utf-8") == '{"model": "example"}\n'
    assert not (destination / "addons/cache").exists()
    assert not (destination / "addons/operations").exists()


def test_restore_rejects_links_and_traversal(tmp_path: Path) -> None:
    for name, linkname in (("../state.json", ""), ("addons/state.json", "../../outside")):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            member = tarfile.TarInfo(name)
            if linkname:
                member.type = tarfile.SYMTYPE
                member.linkname = linkname
            else:
                member.size = 2
                archive.addfile(member, io.BytesIO(b"{}"))
            if linkname:
                archive.addfile(member)
        buffer.seek(0)
        with tarfile.open(fileobj=buffer, mode="r:gz") as archive, pytest.raises(ValueError):
            _restore_config_members(archive, tmp_path / "restore")


def test_restore_rejects_case_folded_duplicate_paths(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name in ("Config.yaml", "config.yaml"):
            member = tarfile.TarInfo(name)
            member.size = 2
            archive.addfile(member, io.BytesIO(b"{}"))
    buffer.seek(0)

    with tarfile.open(fileobj=buffer, mode="r:gz") as archive, pytest.raises(ValueError, match="Duplicate"):
        _restore_config_members(archive, tmp_path / "restore")
