"""Filesystem layout for controller-owned add-on data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from boneio.addons.models import validate_addon_id, validate_logical_path, validate_release_version


@dataclass(frozen=True)
class AddonPaths:
    config_dir: Path

    @classmethod
    def from_config_file(cls, config_file: str | Path) -> AddonPaths:
        return cls(Path(config_file).expanduser().resolve().parent)

    @property
    def root(self) -> Path:
        return self.config_dir / "addons"

    @property
    def repositories(self) -> Path:
        return self.root / "repositories.json"

    @property
    def state(self) -> Path:
        return self.root / "state.json"

    @property
    def lock(self) -> Path:
        return self.root / ".mutation.lock"

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def installed(self) -> Path:
        return self.root / "installed"

    @property
    def staging(self) -> Path:
        return self.root / ".staging"

    @property
    def snapshots(self) -> Path:
        return self.root / "snapshots"

    @property
    def operations(self) -> Path:
        return self.root / "operations"

    def install_dir(self, addon_id: str, version: str) -> Path:
        validate_addon_id(addon_id)
        validate_release_version(version)
        return self.installed / addon_id / version

    def installed_file(self, addon_id: str, version: str, logical_path: str) -> Path:
        validate_logical_path(logical_path)
        base = self.install_dir(addon_id, version)
        target = (base / "files" / logical_path).resolve()
        if not target.is_relative_to(base.resolve()):
            raise ValueError("logical path escapes the installation directory")
        return target

    def ensure(self) -> None:
        for path in (self.root, self.cache, self.installed, self.staging, self.snapshots, self.operations):
            path.mkdir(parents=True, exist_ok=True, mode=0o750)
