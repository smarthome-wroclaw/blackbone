#!/usr/bin/env bash
# Interactive migration from the stock Black app package to blackbone.
# Designed to work both as a local script and through:
#   curl -fsSL https://raw.githubusercontent.com/smarthome-wroclaw/blackbone/main/install.sh | bash

set -Eeuo pipefail

readonly PACKAGE_NAME="blackbone"
readonly SERVICE_NAME="boneio"

info() {
  printf '\033[1;34m[blackbone]\033[0m %s\n' "$*"
}

success() {
  printf '\033[1;32m[blackbone]\033[0m %s\n' "$*"
}

fail() {
  printf '\033[1;31m[blackbone]\033[0m %s\n' "$*" >&2
  exit 1
}

ask_yes_no() {
  local prompt="$1"
  local answer
  printf '%s [Y/n]: ' "$prompt" >&3
  IFS= read -r answer <&3 || true
  case "${answer:-y}" in
    y|Y|yes|YES|Yes) return 0 ;;
    *) return 1 ;;
  esac
}

find_venv() {
  local candidate
  for candidate in \
    "/home/boneio/boneio/venv" \
    "${HOME}/boneio/venv" \
    "${HOME}/venv" \
    "/opt/boneio/venv"; do
    if [[ -x "${candidate}/bin/python" && -x "${candidate}/bin/pip" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

backup_configuration() {
  local archive="$1"
  local -a config_files=()
  local path

  while IFS= read -r -d '' path; do
    config_files+=("${path#"${APP_DIR}/"}")
  done < <(
    find "$APP_DIR" \
      -mindepth 1 -maxdepth 2 \
      -path "${BACKUP_ROOT}" -prune -o \
      -type f \( -name '*.yaml' -o -name '*.yml' \) -print0
  )

  if [[ ${#config_files[@]} -eq 0 ]]; then
    fail "No YAML configuration files were found in ${APP_DIR}."
  fi
  tar -C "$APP_DIR" -czf "$archive" "${config_files[@]}"
  success "Configuration backup created: ${archive}"
}

backup_current_app() {
  local archive="$1"
  local site_packages
  local path
  local -a app_files=("bin/boneio")

  site_packages="$($PYTHON_BIN -c 'import site; print(site.getsitepackages()[0])')"
  while IFS= read -r -d '' path; do
    app_files+=("${path#"${VENV_DIR}/"}")
  done < <(
    find "$site_packages" -maxdepth 1 \
      \( -name 'boneio' -o -name 'boneio-*.dist-info' -o -name 'boneio-*.egg-info' \) \
      -print0
  )

  if [[ ${#app_files[@]} -le 1 ]]; then
    fail "The installed application files were not found in ${site_packages}."
  fi
  tar -C "$VENV_DIR" -czf "$archive" "${app_files[@]}"
  success "Application backup created: ${archive}"
}

if [[ ! -r /dev/tty || ! -w /dev/tty ]]; then
  fail "This installer requires an interactive terminal. Run it from an SSH session."
fi
exec 3<>/dev/tty

command -v tar >/dev/null 2>&1 || fail "The tar command is not available."
command -v systemctl >/dev/null 2>&1 || fail "The systemctl command is not available."

VENV_DIR="$(find_venv)" || fail "The application's Python virtual environment was not found."
readonly VENV_DIR
readonly APP_DIR="$(dirname "$VENV_DIR")"
readonly PYTHON_BIN="${VENV_DIR}/bin/python"
readonly PIP_BIN="${VENV_DIR}/bin/pip"
readonly TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
readonly BACKUP_ROOT="${APP_DIR}/backups/blackbone_migration_${TIMESTAMP}"

if [[ $EUID -eq 0 ]]; then
  SUDO=()
else
  command -v sudo >/dev/null 2>&1 || fail "sudo is not available; run the installer as root."
  info "Checking permission to restart the service. Sudo may ask for your password."
  sudo -v <&3 || fail "Could not obtain sudo privileges."
  SUDO=(sudo)
fi
readonly -a SUDO

current_version="$($PYTHON_BIN -c 'from boneio.version import __version__; print(__version__)' 2>/dev/null || printf 'unknown')"
info "Detected application directory: ${APP_DIR}"
info "Current version: ${current_version}"
info "Target PyPI package: ${PACKAGE_NAME}"

backup_config=false
backup_app=false
if ask_yes_no "Create a backup of the current configuration?"; then
  backup_config=true
fi
if ask_yes_no "Create a backup of the currently installed application?"; then
  backup_app=true
fi

if [[ $backup_config == true || $backup_app == true ]]; then
  mkdir -p "$BACKUP_ROOT"
fi
if [[ $backup_config == true ]]; then
  backup_configuration "${BACKUP_ROOT}/configuration_${TIMESTAMP}.tar.gz"
fi
if [[ $backup_app == true ]]; then
  backup_current_app "${BACKUP_ROOT}/stock_black_app_${current_version}_${TIMESTAMP}.tar.gz"
fi

info "Downloading and installing the latest ${PACKAGE_NAME} package from PyPI..."
"$PIP_BIN" install --upgrade --force-reinstall "$PACKAGE_NAME"

installed_version="$($PYTHON_BIN -c \
  'from importlib.metadata import version; from boneio.version import __version__; print(f"{version(\"blackbone\")} ({__version__})")' \
)" || fail "The package was installed, but application verification failed."
success "Installed ${PACKAGE_NAME} ${installed_version}."

info "Restarting the ${SERVICE_NAME} service..."
"${SUDO[@]}" systemctl restart "$SERVICE_NAME"
sleep 3
if ! "${SUDO[@]}" systemctl is-active --quiet "$SERVICE_NAME"; then
  "${SUDO[@]}" systemctl status "$SERVICE_NAME" --no-pager -n 30 || true
  fail "The service did not start after installation. Any created backups remain in ${BACKUP_ROOT}."
fi

success "Migration complete. The ${SERVICE_NAME} service is running."
if [[ $backup_config == true || $backup_app == true ]]; then
  info "Backups are stored in: ${BACKUP_ROOT}"
fi
