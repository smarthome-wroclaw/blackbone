"""Static safety checks for the curl-friendly blackbone installer."""

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
INSTALLER = PROJECT_ROOT / "scripts" / "install-blackbone.sh"


def test_installer_has_valid_bash_syntax():
    result = subprocess.run(
        ["bash", "-n", str(INSTALLER)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_installer_is_interactive_when_piped_from_curl():
    content = INSTALLER.read_text(encoding="utf-8")

    assert "exec 3<>/dev/tty" in content
    assert "Create a backup of the current configuration?" in content
    assert "Create a backup of the currently installed application?" in content


def test_installer_targets_blackbone_and_verifies_service():
    content = INSTALLER.read_text(encoding="utf-8")

    assert 'readonly PACKAGE_NAME="blackbone"' in content
    assert 'install --upgrade --force-reinstall "$PACKAGE_NAME"' in content
    assert 'systemctl is-active --quiet "$SERVICE_NAME"' in content
