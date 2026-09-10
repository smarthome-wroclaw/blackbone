"""Install declarative add-ons without allowing third-party code execution."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

import yaml
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from boneio.version import __version__

_ADDON_ID = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024


class _NoRedirect(HTTPRedirectHandler):
    """Make redirect responses fail before a second request is sent."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, D102
        return None


class AddonError(Exception):
    """A user-safe error raised while handling an add-on."""


class AddonService:
    """Repository and installed-state manager for Modbus device packs.

    The service only materializes validated JSON files under the controller
    configuration directory. It deliberately has no support for entry points,
    scripts, packages, or executable payloads.
    """

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir.resolve()
        self.root = self.config_dir / "addons"
        self.repositories_path = self.root / "repositories.yaml"
        self.state_path = self.root / "state.json"
        self.devices_dir = self.config_dir / "modbus_devices"

    def list_state(self) -> dict:
        state = self._read_state()
        return {
            "repositories": self._read_repositories(),
            "installed": list(state["installed"].values()),
        }

    def add_repository(self, url: str) -> dict:
        url = self._normalise_registry_url(url)
        repositories = self._read_repositories()
        if any(item["url"] == url for item in repositories):
            raise AddonError("Repository is already configured")
        repositories.append({"id": self._repository_id(url), "url": url, "trust": "custom", "enabled": True})
        self._write_repositories(repositories)
        return repositories[-1]

    def remove_repository(self, repository_id: str) -> None:
        state = self._read_state()
        repositories = self._read_repositories()
        repository = next((item for item in repositories if item["id"] == repository_id), None)
        if repository is None:
            raise AddonError("Repository not found")
        if repository["trust"] == "official":
            raise AddonError("The official repository cannot be removed")
        if any(item["repository"] == repository["url"] for item in state["installed"].values()):
            raise AddonError("Remove its installed add-ons before removing this repository")
        self._write_repositories([item for item in repositories if item["id"] != repository_id])

    def catalog(self) -> dict:
        entries: list[dict] = []
        errors: list[dict] = []
        for repository in self._read_repositories():
            if not repository.get("enabled", True):
                continue
            try:
                index = self._download_json(urljoin(repository["url"] + "/", "index.json"))
                if index.get("schema_version") != 1 or not isinstance(index.get("addons"), list):
                    raise AddonError("Registry has an unsupported index format")
                for raw in index["addons"]:
                    entry = self._validate_catalog_entry(raw, repository)
                    entries.append(entry)
            except AddonError as exc:
                errors.append({"repository": repository["url"], "error": str(exc)})
        installed = self._read_state()["installed"]
        for entry in entries:
            current = installed.get(entry["id"])
            entry["installed_version"] = current["version"] if current else None
            entry["installed"] = current is not None
        return {"addons": entries, "errors": errors}

    def install(self, addon_id: str, repository_url: str, version: str | None = None) -> dict:
        addon_id = self._validate_addon_id(addon_id)
        repository_url = self._normalise_registry_url(repository_url)
        repository = next((item for item in self._read_repositories() if item["url"] == repository_url), None)
        if repository is None:
            raise AddonError("Repository is not configured")
        catalog = self.catalog()["addons"]
        candidates = [item for item in catalog if item["id"] == addon_id and item["repository"] == repository_url]
        if version:
            candidates = [item for item in candidates if item["version"] == version]
        if len(candidates) != 1:
            raise AddonError("Add-on version was not found in the configured repository")
        entry = candidates[0]
        manifest_url = self._same_origin_url(repository_url, entry["manifest_url"])
        manifest_bytes = self._download_bytes(manifest_url)
        if hashlib.sha256(manifest_bytes).hexdigest() != entry["manifest_sha256"]:
            raise AddonError("Manifest checksum does not match the registry")
        try:
            manifest = yaml.safe_load(manifest_bytes) or {}
        except yaml.YAMLError as exc:
            raise AddonError("Manifest is not valid YAML") from exc
        files = self._validate_manifest(manifest, addon_id, entry["version"], repository_url)
        return self._install_files(manifest, files, repository_url)

    def remove(self, addon_id: str) -> dict:
        addon_id = self._validate_addon_id(addon_id)
        state = self._read_state()
        installed = state["installed"].get(addon_id)
        if installed is None:
            raise AddonError("Add-on is not installed")
        self._snapshot(addon_id, installed["files"])
        for relative in installed["files"]:
            target = self._safe_destination(relative, addon_id)
            target.unlink(missing_ok=True)
        shutil.rmtree(self.devices_dir / addon_id, ignore_errors=True)
        del state["installed"][addon_id]
        self._write_state(state)
        return {"id": addon_id, "removed": True, "restart_required": True}

    def _install_files(self, manifest: dict, files: list[dict], repository_url: str) -> dict:
        addon_id = manifest["id"]
        state = self._read_state()
        state_before = json.loads(json.dumps(state))
        existing = state["installed"].get(addon_id)
        previous_files = existing["files"] if existing else []
        destinations = [item["destination"] for item in files]
        snapshot = self._snapshot(addon_id, previous_files + destinations)
        stage = Path(tempfile.mkdtemp(prefix="blackbone-addon-", dir=self.root if self.root.exists() else self.config_dir))
        try:
            for item in files:
                source_url = self._same_origin_url(repository_url, item["source"])
                payload = self._download_bytes(source_url)
                if hashlib.sha256(payload).hexdigest() != item["sha256"]:
                    raise AddonError(f"Checksum failed for {item['source']}")
                model = self._validate_device_json(payload, item["source"])
                self._ensure_model_is_available(model, addon_id)
                staged = stage / item["destination"]
                staged.parent.mkdir(parents=True, exist_ok=True)
                staged.write_bytes(payload)
            for old_file in set(previous_files) - set(destinations):
                self._safe_destination(old_file, addon_id).unlink(missing_ok=True)
            for item in files:
                target = self._safe_destination(item["destination"], addon_id)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(stage / item["destination"], target)
            state["installed"][addon_id] = {
                "id": addon_id,
                "name": manifest["name"],
                "version": manifest["version"],
                "type": manifest["type"],
                "repository": repository_url,
                "installed_at": datetime.now(UTC).isoformat(),
                "enabled": True,
                "files": destinations,
            }
            self._write_state(state)
            return {**state["installed"][addon_id], "restart_required": True}
        except Exception:
            self._restore_snapshot(snapshot, previous_files + destinations, addon_id)
            self._write_state(state_before)
            raise
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def _validate_catalog_entry(self, raw: object, repository: dict) -> dict:
        if not isinstance(raw, dict):
            raise AddonError("Registry contains an invalid add-on entry")
        addon_id = self._validate_addon_id(raw.get("id"))
        version = self._validate_version(raw.get("version"))
        if raw.get("type") != "modbus_device_pack":
            raise AddonError(f"{addon_id} uses an unsupported add-on type")
        checksum = raw.get("manifest_sha256")
        if not isinstance(checksum, str) or not _SHA256.fullmatch(checksum):
            raise AddonError(f"{addon_id} has an invalid manifest checksum")
        if not isinstance(raw.get("manifest_url"), str):
            raise AddonError(f"{addon_id} has no manifest URL")
        self._same_origin_url(repository["url"], raw["manifest_url"])
        compatible = self._is_compatible(raw.get("min_blackbone_version"), raw.get("max_blackbone_version"))
        return {**raw, "id": addon_id, "version": version, "repository": repository["url"], "trust": repository["trust"], "compatible": compatible}

    def _validate_manifest(self, manifest: object, addon_id: str, version: str, repository_url: str) -> list[dict]:
        if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
            raise AddonError("Manifest has an unsupported format")
        if self._validate_addon_id(manifest.get("id")) != addon_id or self._validate_version(manifest.get("version")) != version:
            raise AddonError("Manifest identity does not match the registry")
        if manifest.get("type") != "modbus_device_pack" or not isinstance(manifest.get("name"), str):
            raise AddonError("Manifest is not a supported Modbus device pack")
        blackbone = manifest.get("blackbone", {})
        if not isinstance(blackbone, dict) or not self._is_compatible(blackbone.get("min_version"), blackbone.get("max_version")):
            raise AddonError("Add-on is not compatible with this BlackBone version")
        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            raise AddonError("Manifest does not contain any files")
        validated: list[dict] = []
        for item in files:
            if not isinstance(item, dict) or not isinstance(item.get("source"), str) or not isinstance(item.get("destination"), str):
                raise AddonError("Manifest has an invalid file entry")
            self._same_origin_url(repository_url, item["source"])
            destination = item["destination"]
            self._safe_destination(destination, addon_id)
            checksum = item.get("sha256")
            if not isinstance(checksum, str) or not _SHA256.fullmatch(checksum):
                raise AddonError(f"Manifest has an invalid checksum for {item['source']}")
            validated.append({"source": item["source"], "destination": destination, "sha256": checksum})
        return validated

    def _validate_device_json(self, payload: bytes, name: str) -> str:
        try:
            data = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AddonError(f"{name} is not valid JSON") from exc
        if not isinstance(data, dict) or not isinstance(data.get("model"), str) or not isinstance(data.get("registers_base", []), list):
            raise AddonError(f"{name} is not a valid Modbus device definition")
        return data["model"]

    def _ensure_model_is_available(self, model: str, addon_id: str) -> None:
        """Reject catalog collisions rather than letting add-ons shadow models."""
        core_dir = Path(__file__).parents[1] / "modbus" / "devices"
        for root in (core_dir, self.devices_dir):
            if not root.is_dir():
                continue
            for candidate in root.rglob("*.json"):
                if candidate.is_relative_to(self.devices_dir / addon_id):
                    continue
                try:
                    if json.loads(candidate.read_text()).get("model") == model:
                        raise AddonError(f"Modbus model '{model}' is already provided by another catalog")
                except (OSError, json.JSONDecodeError):
                    continue

    def _read_repositories(self) -> list[dict]:
        if not self.repositories_path.exists():
            return []
        try:
            data = yaml.safe_load(self.repositories_path.read_text()) or {}
            repositories = data.get("repositories", [])
            return repositories if isinstance(repositories, list) else []
        except (OSError, yaml.YAMLError):
            return []

    def _write_repositories(self, repositories: list[dict]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self.repositories_path, yaml.safe_dump({"schema_version": 1, "repositories": repositories}, sort_keys=False))

    def _read_state(self) -> dict:
        if not self.state_path.exists():
            return {"schema_version": 1, "installed": {}}
        try:
            data = json.loads(self.state_path.read_text())
            if isinstance(data, dict) and isinstance(data.get("installed"), dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
        return {"schema_version": 1, "installed": {}}

    def _write_state(self, state: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self.state_path, json.dumps(state, indent=2, sort_keys=True) + "\n")

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content)
        os.replace(temporary, path)

    def _snapshot(self, addon_id: str, relative_files: list[str]) -> Path:
        # A rollback snapshot is deliberately small and local. Existing config
        # backups remain the recovery mechanism for whole-controller changes.
        snapshot_dir = self.root / "snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot = snapshot_dir / f"{addon_id}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}.json"
        contents: dict[str, str] = {}
        for relative in relative_files:
            target = self._safe_destination(relative, addon_id)
            if target.exists():
                contents[relative] = target.read_text()
        snapshot.write_text(json.dumps({"files": contents}, sort_keys=True))
        return snapshot

    def _restore_snapshot(self, snapshot: Path, affected_files: list[str], addon_id: str) -> None:
        """Restore every affected target after an interrupted install/update."""
        try:
            contents = json.loads(snapshot.read_text()).get("files", {})
            for relative in set(affected_files):
                target = self._safe_destination(relative, addon_id)
                if relative not in contents:
                    target.unlink(missing_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(contents[relative])
        except (OSError, json.JSONDecodeError) as exc:
            raise AddonError("Add-on operation failed and its rollback could not be completed") from exc

    def _safe_destination(self, relative: str, addon_id: str) -> Path:
        expected_prefix = f"modbus_devices/{addon_id}/"
        if not relative.startswith(expected_prefix) or not relative.endswith(".json"):
            raise AddonError("Add-on may only write JSON device files in its own directory")
        target = (self.config_dir / relative).resolve()
        allowed = (self.devices_dir / addon_id).resolve()
        if not target.is_relative_to(allowed):
            raise AddonError("Add-on destination escapes its data directory")
        return target

    @staticmethod
    def _validate_addon_id(value: object) -> str:
        if not isinstance(value, str) or not _ADDON_ID.fullmatch(value):
            raise AddonError("Add-on ID must use lowercase letters, digits, dots, dashes, or underscores")
        return value

    @staticmethod
    def _validate_version(value: object) -> str:
        if not isinstance(value, str):
            raise AddonError("Add-on version is missing")
        try:
            Version(value)
        except Exception as exc:
            raise AddonError("Add-on version is invalid") from exc
        return value

    @staticmethod
    def _normalise_registry_url(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            raise AddonError("Repository URL must be a clean HTTPS URL")
        return url.rstrip("/")

    @staticmethod
    def _repository_id(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:12]

    @staticmethod
    def _same_origin_url(repository_url: str, path: str) -> str:
        resolved = urljoin(repository_url.rstrip("/") + "/", path)
        repository = urlparse(repository_url)
        target = urlparse(resolved)
        if target.scheme != "https" or target.netloc != repository.netloc:
            raise AddonError("Registry file URL must stay on the repository origin")
        return resolved

    @staticmethod
    def _is_compatible(minimum: object, maximum: object) -> bool:
        try:
            specifier = SpecifierSet((f">={minimum}" if minimum else "") + (f",{maximum}" if maximum else ""))
            return Version(__version__) in specifier
        except Exception:
            return False

    @staticmethod
    def _download_bytes(url: str) -> bytes:
        try:
            request = Request(url, headers={"User-Agent": "BlackBone-Addons/1"})
            with build_opener(_NoRedirect()).open(request, timeout=10) as response:  # noqa: S310 - URLs are validated registry HTTPS URLs.
                payload = response.read(_MAX_DOWNLOAD_BYTES + 1)
                if len(payload) > _MAX_DOWNLOAD_BYTES:
                    raise AddonError("Registry file is too large")
                return payload
        except (HTTPError, URLError, OSError) as exc:
            raise AddonError(f"Could not download registry file: {exc}") from exc

    @classmethod
    def _download_json(cls, url: str) -> dict:
        try:
            data = json.loads(cls._download_bytes(url))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AddonError("Registry index is not valid JSON") from exc
        if not isinstance(data, dict):
            raise AddonError("Registry index must be a JSON object")
        return data
