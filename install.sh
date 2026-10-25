#!/usr/bin/env bash
# Interactive migration from the stock Black app package to blackbone.
# Designed to work both as a local script and through:
#   curl -fsSL https://raw.githubusercontent.com/smarthome-wroclaw/blackbone/main/install.sh | bash

set -Eeuo pipefail

readonly PACKAGE_NAME="blackbone"
readonly LEGACY_PACKAGE_NAME="boneio"
readonly SERVICE_NAME="boneio"
readonly PACKAGE_SPEC="${BLACKBONE_PACKAGE_PATH:-${PACKAGE_NAME}}"
readonly VERIFY_CODE='from importlib.metadata import version; from boneio.version import __version__; print(version("blackbone"), f"({__version__})")'

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

backup_migration_trust() {
  local archive="$1"
  local path
  local -a existing_paths=()
  local -a trust_paths=(
    etc/boneio/migrations.pem
    etc/boneio/migrations-recovery.pem
    usr/lib/boneio/trusted
    usr/lib/boneio/proxy-config
    usr/sbin/boneio-migrate
    usr/sbin/boneio-migrate-v2
    usr/sbin/boneio-helpers-heal
    usr/sbin/boneio-containers
    usr/sbin/boneio-system
    etc/sudoers.d/boneio-migrate
    etc/sudoers.d/boneio-helpers
    etc/systemd/system/boneio-helpers-heal.service
  )

  for path in "${trust_paths[@]}"; do
    if "${SUDO[@]}" test -e "/${path}"; then
      existing_paths+=("${path}")
    fi
  done

  if [[ ${#existing_paths[@]} -eq 0 ]]; then
    info "No existing migration trust files to back up."
    return 0
  fi

  mkdir -p "$(dirname "$archive")"
  "${SUDO[@]}" tar -C / -czf "$archive" "${existing_paths[@]}"
  "${SUDO[@]}" chown "$(id -u):$(id -g)" "$archive"
  chmod 600 "$archive"
  success "Previous migration trust state backed up: ${archive}"
}

install_fork_migration_trust() {
  local assets_dir="$1"
  local name

  [[ -r "${assets_dir}/migrations.pem" ]] || fail "The fork release key is missing from ${assets_dir}."
  [[ -r "${assets_dir}/migrations-recovery.pem" ]] || fail "The fork recovery key is missing from ${assets_dir}."
  openssl pkey -pubin -in "${assets_dir}/migrations.pem" -text -noout 2>/dev/null \
    | grep -q ED25519 || fail "The fork release key is not a valid Ed25519 public key."
  openssl pkey -pubin -in "${assets_dir}/migrations-recovery.pem" -text -noout 2>/dev/null \
    | grep -q ED25519 || fail "The fork recovery key is not a valid Ed25519 public key."
  if cmp -s "${assets_dir}/migrations.pem" "${assets_dir}/migrations-recovery.pem"; then
    fail "The fork release and recovery keys must be different."
  fi

  "${SUDO[@]}" install -d -o root -g root -m 0755 \
    /etc/boneio /usr/lib/boneio/trusted /usr/lib/boneio

  for name in migrations.pem migrations-recovery.pem; do
    "${SUDO[@]}" install -o root -g root -m 0444 \
      "${assets_dir}/${name}" "/etc/boneio/${name}"
    "${SUDO[@]}" install -o root -g root -m 0444 \
      "${assets_dir}/${name}" "/usr/lib/boneio/trusted/${name}"
  done

  for name in boneio-migrate-v2 boneio-containers boneio-system boneio-helpers-heal; do
    "${SUDO[@]}" install -o root -g root -m 0755 \
      "${assets_dir}/helpers/${name}" "/usr/lib/boneio/trusted/${name}"
    "${SUDO[@]}" install -o root -g root -m 0755 \
      "${assets_dir}/helpers/${name}" "/usr/sbin/${name}"
  done

  "${SUDO[@]}" install -o root -g root -m 0755 \
    "${assets_dir}/helpers/boneio-proxy-config" \
    /usr/lib/boneio/trusted/boneio-proxy-config
  "${SUDO[@]}" install -o root -g root -m 0755 \
    "${assets_dir}/helpers/boneio-proxy-config" /usr/lib/boneio/proxy-config

  "${SUDO[@]}" install -o root -g root -m 0644 \
    "${assets_dir}/docker/nodered/docker-compose.yaml" \
    /usr/lib/boneio/trusted/docker-compose.yaml
  "${SUDO[@]}" install -o root -g root -m 0644 \
    "${assets_dir}/docker/nodered/docker-compose-cloud.yaml" \
    /usr/lib/boneio/trusted/docker-compose-cloud.yaml

  "${SUDO[@]}" visudo -cf "${assets_dir}/sudoers/boneio-helpers" \
    || fail "The fork's privileged helper rules failed validation."
  "${SUDO[@]}" install -o root -g root -m 0440 \
    "${assets_dir}/sudoers/boneio-helpers" \
    /usr/lib/boneio/trusted/sudoers-boneio-helpers
  "${SUDO[@]}" install -o root -g root -m 0440 \
    "${assets_dir}/sudoers/boneio-helpers" /etc/sudoers.d/boneio-helpers

  "${SUDO[@]}" install -o root -g root -m 0644 \
    "${assets_dir}/systemd/boneio-helpers-heal.service" \
    /etc/systemd/system/boneio-helpers-heal.service
  "${SUDO[@]}" systemctl daemon-reload
  "${SUDO[@]}" systemctl enable boneio-helpers-heal.service
  "${SUDO[@]}" /usr/sbin/boneio-helpers-heal
  "${SUDO[@]}" /usr/sbin/boneio-migrate-v2 --selftest \
    || fail "The fork's privileged migration helper failed its self-test."

  success "Migration helper and trust anchors now use this BlackBone fork."
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
if [[ -n "${BLACKBONE_PACKAGE_PATH:-}" && ! -r "${BLACKBONE_PACKAGE_PATH}" ]]; then
  fail "BLACKBONE_PACKAGE_PATH is set, but the package file is not readable: ${BLACKBONE_PACKAGE_PATH}"
fi
info "Target package: ${PACKAGE_SPEC}"

backup_config=false
backup_app=false
if ask_yes_no "Create a backup of the current configuration?"; then
  backup_config=true
fi
if ask_yes_no "Create a backup of the currently installed application?"; then
  backup_app=true
fi

mkdir -p "$BACKUP_ROOT"
if [[ $backup_config == true ]]; then
  backup_configuration "${BACKUP_ROOT}/configuration_${TIMESTAMP}.tar.gz"
fi
if [[ $backup_app == true ]]; then
  backup_current_app "${BACKUP_ROOT}/stock_black_app_${current_version}_${TIMESTAMP}.tar.gz"
fi

backup_migration_trust "${BACKUP_ROOT}/migration_trust_${TIMESTAMP}.tar.gz"

if "$PIP_BIN" show "$LEGACY_PACKAGE_NAME" >/dev/null 2>&1; then
  info "Removing the legacy ${LEGACY_PACKAGE_NAME} distribution..."
  "$PIP_BIN" uninstall --yes "$LEGACY_PACKAGE_NAME"
fi

info "Installing ${PACKAGE_SPEC}..."
"$PIP_BIN" install --upgrade --force-reinstall "$PACKAGE_SPEC"

installed_version="$($PYTHON_BIN -c "$VERIFY_CODE")" \
  || fail "The package was installed, but application verification failed."
success "Installed ${PACKAGE_NAME} ${installed_version}."

info "Stopping the service before replacing the migration trust anchors..."
"${SUDO[@]}" systemctl stop "$SERVICE_NAME"

migration_assets="$($PYTHON_BIN -c 'from pathlib import Path; import boneio; print(Path(boneio.__file__).parent / "migrations" / "assets")')"
install_fork_migration_trust "$migration_assets"

info "Restarting the ${SERVICE_NAME} service..."
"${SUDO[@]}" systemctl restart "$SERVICE_NAME"
sleep 3
if ! "${SUDO[@]}" systemctl is-active --quiet "$SERVICE_NAME"; then
  "${SUDO[@]}" systemctl status "$SERVICE_NAME" --no-pager -n 30 || true
  fail "The service did not start after installation. Any created backups remain in ${BACKUP_ROOT}."
fi

success "Migration complete. The ${SERVICE_NAME} service is running."
info "Rollback data, including any previous migration trust state, is stored in: ${BACKUP_ROOT}"
