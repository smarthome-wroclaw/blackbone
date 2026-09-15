"""Download and materialize a declarative package in a private staging area."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml
from packaging.specifiers import SpecifierSet
from packaging.version import Version
from pydantic import ValidationError

from boneio.addons.errors import AddonError
from boneio.addons.models import AddonManifest, IndexAddon, Repository
from boneio.addons.network import FILE_LIMIT, MANIFEST_LIMIT, SafeFetcher, resolve_same_origin
from boneio.addons.paths import AddonPaths
from boneio.addons.storage import atomic_write_bytes
from boneio.modbus.device_definition import validate_definition
from boneio.version import __version__


@dataclass(frozen=True)
class StagedPackage:
    root: Path
    manifest: AddonManifest
    manifest_bytes: bytes
    models: tuple[str, ...]


class PackageValidator:
    def __init__(self, paths: AddonPaths, fetcher: SafeFetcher) -> None:
        self.paths = paths
        self.fetcher = fetcher

    async def fetch_manifest(self, repository: Repository, release: IndexAddon) -> tuple[AddonManifest, bytes, str]:
        manifest_url = resolve_same_origin(str(repository.url), release.manifest_url)
        result = await self.fetcher.fetch(manifest_url, limit=MANIFEST_LIMIT)
        payload = result.body or b""
        digest = hashlib.sha256(payload).hexdigest()
        if digest != release.manifest_sha256:
            raise AddonError("manifest_hash_mismatch", "Manifest checksum does not match the repository index.")
        try:
            raw = yaml.safe_load(payload)
            manifest = AddonManifest.model_validate(raw)
        except (yaml.YAMLError, UnicodeDecodeError, ValidationError) as exc:
            raise AddonError(
                "invalid_manifest", "Add-on manifest is invalid.", details={"errors": _safe_errors(exc)}
            ) from exc
        if manifest.id != release.id or manifest.version != release.version or manifest.type != release.type:
            raise AddonError("manifest_identity_mismatch", "Manifest identity does not match the repository index.")
        if manifest.blackbone.version != release.blackbone.version:
            raise AddonError(
                "manifest_compatibility_mismatch", "Manifest compatibility does not match the repository index."
            )
        if Version(__version__) not in SpecifierSet(manifest.blackbone.version):
            raise AddonError(
                "incompatible", "This add-on version is not compatible with this BlackBone version.", status_code=409
            )
        return manifest, payload, manifest_url

    async def stage(
        self,
        operation_id: str,
        repository: Repository,
        release: IndexAddon,
    ) -> StagedPackage:
        manifest, manifest_bytes, manifest_url = await self.fetch_manifest(repository, release)
        root = self.paths.staging / operation_id
        if root.exists():
            shutil.rmtree(root)
        (root / "files" / "modbus_devices").mkdir(parents=True, mode=0o750)
        atomic_write_bytes(root / "manifest.yaml", manifest_bytes)
        models: list[str] = []
        try:
            for declared in manifest.files:
                file_url = resolve_same_origin(manifest_url, declared.path)
                result = await self.fetcher.fetch(file_url, limit=FILE_LIMIT)
                payload = result.body or b""
                if hashlib.sha256(payload).hexdigest() != declared.sha256:
                    raise AddonError(
                        "file_hash_mismatch",
                        "Downloaded file checksum does not match its manifest.",
                        details={"file": declared.path},
                    )
                try:
                    decoded = json.loads(payload.decode("utf-8"))
                    validate_definition(decoded)
                except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
                    raise AddonError(
                        "invalid_device_definition",
                        "A Modbus device definition is invalid.",
                        details={"file": declared.path, "errors": _safe_errors(exc)},
                    ) from exc
                model_key = Path(declared.path).stem
                models.append(model_key)
                target = root / "files" / declared.path
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
                atomic_write_bytes(target, payload)
            return StagedPackage(root, manifest, manifest_bytes, tuple(models))
        except Exception:
            shutil.rmtree(root, ignore_errors=True)
            raise


def _safe_errors(exc: Exception) -> list[dict[str, object]]:
    if isinstance(exc, ValidationError):
        return [
            {"location": ".".join(str(part) for part in item["loc"]), "message": item["msg"], "type": item["type"]}
            for item in exc.errors(include_url=False, include_context=False, include_input=False)
        ]
    return [{"message": "Content could not be parsed."}]
