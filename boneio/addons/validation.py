"""Preview validation and short-lived confirmation tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import shutil
import time
from dataclasses import dataclass
from typing import Literal

from packaging.version import Version

from boneio.addons.errors import AddonError
from boneio.addons.models import IndexAddon
from boneio.addons.package import PackageValidator, StagedPackage
from boneio.addons.registry import RegistryClient
from boneio.addons.storage import AddonStorage
from boneio.modbus import device_registry


@dataclass(frozen=True)
class PreviewBinding:
    repository_id: str
    addon_id: str
    version: str
    manifest_sha256: str
    action: str
    expires_at: int


class AddonValidator:
    def __init__(
        self,
        storage: AddonStorage,
        registry: RegistryClient,
        packages: PackageValidator,
        *,
        secret: bytes | None = None,
        token_ttl: int = 600,
    ) -> None:
        self.storage = storage
        self.registry = registry
        self.packages = packages
        self.secret = secret or secrets.token_bytes(32)
        self.token_ttl = token_ttl
        self._previews: dict[str, PreviewBinding] = {}

    async def preview(
        self,
        addon_id: str,
        repository_id: str,
        version: str,
        action: Literal["install", "update", "downgrade"],
    ) -> dict[str, object]:
        release = self.registry.exact_release(repository_id, addon_id, version)
        installed = self.storage.read_state().installed.get(addon_id)
        self._validate_action(action, installed.version if installed else None, version)
        repository = self.registry.repository(repository_id)
        preview_id = f"preview-{secrets.token_hex(12)}"
        staged = await self.packages.stage(preview_id, repository, release)
        try:
            conflicts = self.conflicts(staged, replacing_addon=addon_id if installed else None)
            if conflicts:
                conflict = conflicts[0]
                raise AddonError(
                    "model_conflict",
                    f"Model '{conflict['model']}' is already provided by another source.",
                    details=conflict,
                    status_code=409,
                )
            binding = PreviewBinding(
                repository_id=repository_id,
                addon_id=addon_id,
                version=version,
                manifest_sha256=release.manifest_sha256,
                action=action,
                expires_at=int(time.time()) + self.token_ttl,
            )
            token = self._encode(binding)
            self._previews[token] = binding
            self._purge_expired()
            return {
                "id": addon_id,
                "name": staged.manifest.name,
                "version": version,
                "action": action,
                "repository_id": repository_id,
                "trust": repository.trust,
                "compatible": True,
                "files": [item.model_dump(mode="json") for item in staged.manifest.files],
                "models": list(staged.models),
                "conflicts": [],
                "reload_required": True,
                "confirmation_token": token,
                "expires_at": binding.expires_at,
            }
        finally:
            shutil.rmtree(staged.root, ignore_errors=True)

    def verify(self, token: str, addon_id: str, allowed_actions: set[str]) -> PreviewBinding:
        self._purge_expired()
        binding = self._decode(token)
        cached = self._previews.get(token)
        if cached != binding:
            raise AddonError("preview_expired", "Preview has expired; review the add-on again.", status_code=409)
        if binding.addon_id != addon_id or binding.action not in allowed_actions:
            raise AddonError("invalid_confirmation", "Confirmation does not match this operation.", status_code=409)
        return binding

    def consume(self, token: str) -> None:
        self._previews.pop(token, None)

    def conflicts(self, package: StagedPackage, replacing_addon: str | None = None) -> list[dict[str, str]]:
        conflicts: list[dict[str, str]] = []
        existing = {ref.key: ref.source for ref in device_registry.list_models()}
        for model in package.models:
            owner = existing.get(model)
            if owner is None or (replacing_addon and owner == f"addon:{replacing_addon}"):
                continue
            conflicts.append({"model": model, "owner": owner})
        return conflicts

    def _encode(self, binding: PreviewBinding) -> str:
        payload = json.dumps(binding.__dict__, separators=(",", ":"), sort_keys=True).encode()
        encoded = base64.urlsafe_b64encode(payload).rstrip(b"=")
        signature = hmac.new(self.secret, encoded, hashlib.sha256).digest()
        return f"{encoded.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"

    def _decode(self, token: str) -> PreviewBinding:
        try:
            encoded, signature = token.split(".", 1)
            expected = hmac.new(self.secret, encoded.encode(), hashlib.sha256).digest()
            supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
            if not hmac.compare_digest(expected, supplied):
                raise ValueError
            payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            binding = PreviewBinding(**json.loads(payload))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise AddonError("invalid_confirmation", "Confirmation token is invalid.", status_code=409) from exc
        if binding.expires_at < int(time.time()):
            raise AddonError("preview_expired", "Preview has expired; review the add-on again.", status_code=409)
        return binding

    def _purge_expired(self) -> None:
        now = int(time.time())
        self._previews = {token: item for token, item in self._previews.items() if item.expires_at >= now}

    @staticmethod
    def _validate_action(action: str, installed_version: str | None, requested_version: str) -> None:
        if action == "install" and installed_version is not None:
            raise AddonError("already_installed", "Add-on is already installed.", status_code=409)
        if action in {"update", "downgrade"} and installed_version is None:
            raise AddonError("not_installed", "Add-on is not installed.", status_code=409)
        if action == "update" and installed_version and Version(requested_version) <= Version(installed_version):
            raise AddonError(
                "not_an_upgrade", "Selected version is not newer than the installed version.", status_code=409
            )
        if action == "downgrade" and installed_version and Version(requested_version) >= Version(installed_version):
            raise AddonError(
                "not_a_downgrade", "Selected version is not older than the installed version.", status_code=409
            )
