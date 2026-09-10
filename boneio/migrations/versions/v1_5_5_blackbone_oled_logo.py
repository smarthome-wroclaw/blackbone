"""BlackBone 1.5.5 — BlackBone branding on the OLED splash screens.

The in-app OLED logo is now a BlackBone bitmap, but the boot and shutdown
splash screens are rendered by ``oled_msg.sh`` / ``oled_boot_splash.sh``
straight from the systemd units, using a built-in 5x8 ASCII font. Those can
only show text, so the "boneIO Black" heading becomes "BlackBone".

Controllers that already have the old units in ``/etc/systemd/system`` need
them reinstalled, which is what this migration does.
"""

from __future__ import annotations

from boneio.migrations.actions import (
    InstallFile,
    MigrationAction,
    SystemctlDaemonReload,
)

VERSION = "1.5.5"
DESCRIPTION = "BlackBone branding on OLED boot/shutdown splash screens"
REQUIRES_ROOT = True

_BONEIO_USER = "boneio"
_BONEIO_HOME = f"/home/{_BONEIO_USER}"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.5.5.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    template_vars = {
        "BONEIO_USER": _BONEIO_USER,
        "BONEIO_HOME": _BONEIO_HOME,
    }

    return [
        # Boot splash: shown by the OS before the app starts
        InstallFile(
            src="systemd/boneio-oled-boot.service",
            dst="/etc/systemd/system/boneio-oled-boot.service",
            mode=0o644,
            on_change=SystemctlDaemonReload(),
        ),
        # Late-shutdown splash: shown after the network is down
        InstallFile(
            src="systemd/boneio-oled-shutdown.service",
            dst="/etc/systemd/system/boneio-oled-shutdown.service",
            mode=0o644,
            on_change=SystemctlDaemonReload(),
        ),
        # App start/stop splash
        InstallFile(
            src="systemd/boneio.service",
            dst="/etc/systemd/system/boneio.service",
            mode=0o644,
            template_vars=template_vars,
            on_change=SystemctlDaemonReload(),
        ),
    ]
