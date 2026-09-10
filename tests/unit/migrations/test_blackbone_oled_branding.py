"""Tests for BlackBone branding on the OLED boot/shutdown splash screens.

The splash text is rendered by ``oled_msg.sh`` / ``oled_boot_splash.sh``,
which use a built-in 5x8 ASCII font — no bitmap is possible there, so the
"boneIO Black" string in the systemd units is replaced with "BlackBone".

Because the units live in ``/etc/systemd/system`` on the device, a migration
is required to push the updated files out to controllers that already have
the old ones installed.
"""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path

import pytest

from boneio.migrations.actions import InstallFile, SystemctlDaemonReload

ASSETS_DIR = Path(__file__).resolve().parents[3] / "boneio" / "migrations" / "assets"
SYSTEMD_DIR = ASSETS_DIR / "systemd"
MANIFEST_PATH = ASSETS_DIR / "MANIFEST.sha256"

MIGRATION_MODULE = "boneio.migrations.versions.v1_5_5_blackbone_oled_logo"

SPLASH_UNITS = (
    "boneio.service",
    "boneio-oled-boot.service",
    "boneio-oled-shutdown.service",
)

OLD_BRANDING = "boneIO Black"
NEW_BRANDING = "BlackBone"


# ---------------------------------------------------------------------------
# Asset content
# ---------------------------------------------------------------------------


class TestSystemdSplashBranding:
    """The unit files shipped in the package."""

    @pytest.mark.parametrize("unit", SPLASH_UNITS)
    def test_unit_has_no_boneio_branding_in_splash_text(self, unit):
        content = (SYSTEMD_DIR / unit).read_text(encoding="utf-8")
        assert OLD_BRANDING not in content

    @pytest.mark.parametrize("unit", SPLASH_UNITS)
    def test_unit_shows_blackbone_branding(self, unit):
        content = (SYSTEMD_DIR / unit).read_text(encoding="utf-8")
        splash_lines = [
            line
            for line in content.splitlines()
            if "oled_msg.sh" in line or "oled_boot_splash.sh" in line
        ]
        assert splash_lines, f"{unit} has no OLED splash invocation"
        assert any(NEW_BRANDING in line for line in splash_lines)


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


class TestBlackboneOledMigration:
    """The migration that redeploys the rebranded units."""

    @pytest.fixture()
    def module(self):
        return importlib.import_module(MIGRATION_MODULE)

    def test_declares_version_and_description(self, module):
        assert module.VERSION == "1.5.5"
        assert module.DESCRIPTION
        assert module.REQUIRES_ROOT is True

    def test_version_sorts_after_every_existing_migration(self, module):
        versions_dir = Path(module.__file__).parent
        others = []
        for path in versions_dir.glob("v*.py"):
            mod = importlib.import_module(
                f"boneio.migrations.versions.{path.stem}"
            )
            version = getattr(mod, "VERSION", None)
            if version and version != module.VERSION:
                others.append(tuple(int(p) for p in version.split(".")))
        assert others, "no other migrations discovered"
        new = tuple(int(p) for p in module.VERSION.split("."))
        assert new > max(others)

    def test_installs_all_three_splash_units(self, module):
        installs = [a for a in module.plan() if isinstance(a, InstallFile)]
        installed = {Path(a.src).name for a in installs}
        assert installed == set(SPLASH_UNITS)

    def test_units_are_installed_to_etc_systemd_with_reload(self, module):
        for action in module.plan():
            if isinstance(action, InstallFile):
                assert action.dst == f"/etc/systemd/system/{Path(action.src).name}"
                assert action.mode == 0o644
                assert isinstance(action.on_change, SystemctlDaemonReload)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


class TestAssetManifest:
    """MANIFEST.sha256 gates what the privileged helper is allowed to write."""

    @pytest.mark.parametrize("unit", SPLASH_UNITS)
    def test_manifest_matches_rebranded_unit(self, unit):
        entries = {}
        for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            sha, _, rel = line.partition("  ")
            entries[rel.strip()] = sha

        rel_path = f"systemd/{unit}"
        assert rel_path in entries, f"{rel_path} missing from MANIFEST.sha256"
        actual = hashlib.sha256((SYSTEMD_DIR / unit).read_bytes()).hexdigest()
        assert entries[rel_path] == actual, "MANIFEST.sha256 is stale — rerun scripts/update-migration-manifest.sh"
