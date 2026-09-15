"""Repository configuration, caching, and catalog normalization."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import Version
from pydantic import ValidationError

from boneio.addons.errors import AddonError
from boneio.addons.models import (
    IndexAddon,
    Repository,
    RepositoryIndex,
    RepositoryState,
    RepositoryTrust,
)
from boneio.addons.network import INDEX_LIMIT, SafeFetcher, canonical_repository_url, resolve_same_origin
from boneio.addons.paths import AddonPaths
from boneio.addons.storage import AddonStorage, atomic_write_bytes
from boneio.version import __version__

OFFICIAL_REPOSITORY_ID = "blackbone-community"
OFFICIAL_REPOSITORY_NAME = "BlackBone Community"
OFFICIAL_REPOSITORY_URL = "https://raw.githubusercontent.com/smarthome-wroclaw/blackbone-addons/main/index.json"


def custom_repository_id(url: str) -> str:
    canonical = canonical_repository_url(url)
    return f"custom-{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"


class RegistryClient:
    def __init__(self, paths: AddonPaths, storage: AddonStorage, fetcher: SafeFetcher | None = None) -> None:
        self.paths = paths
        self.storage = storage
        self.fetcher = fetcher or SafeFetcher()
        self._indexes: dict[str, RepositoryIndex] = {}
        self._offline: dict[str, bool] = {}
        self._seed_official()
        self._load_cached_indexes()

    def _seed_official(self) -> None:
        state = self.storage.read_repositories()
        if any(item.id == OFFICIAL_REPOSITORY_ID for item in state.repositories):
            return
        official = Repository(
            id=OFFICIAL_REPOSITORY_ID,
            name=OFFICIAL_REPOSITORY_NAME,
            url=OFFICIAL_REPOSITORY_URL,
            trust=RepositoryTrust.OFFICIAL,
            enabled=True,
        )
        self.storage.write_repositories(state.model_copy(update={"repositories": [official, *state.repositories]}))

    def _cache_path(self, repository_id: str) -> Path:
        return self.paths.cache / f"{repository_id}.json"

    def _read_cache(self, repository: Repository) -> tuple[RepositoryIndex, str | None] | None:
        path = self._cache_path(repository.id)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw.get("url") != str(repository.url):
                return None
            return RepositoryIndex.model_validate(raw["index"]), raw.get("etag")
        except (OSError, json.JSONDecodeError, KeyError, ValidationError, TypeError):
            return None

    def _write_cache(self, repository: Repository, index: RepositoryIndex, etag: str | None) -> None:
        payload = {
            "url": str(repository.url),
            "etag": etag,
            "fetched_at": datetime.now(UTC).isoformat(),
            "index": index.model_dump(mode="json"),
        }
        atomic_write_bytes(self._cache_path(repository.id), json.dumps(payload, sort_keys=True).encode() + b"\n")

    def _load_cached_indexes(self) -> None:
        for repository in self.storage.read_repositories().repositories:
            cached = self._read_cache(repository)
            if cached:
                self._indexes[repository.id] = cached[0]

    async def refresh_one(self, repository: Repository) -> RepositoryIndex:
        cached = self._read_cache(repository)
        etag = cached[1] if cached else None
        try:
            result = await self.fetcher.fetch(str(repository.url), limit=INDEX_LIMIT, etag=etag)
            if result.not_modified:
                if not cached:
                    raise AddonError(
                        "invalid_cache", "Repository returned 304 without a cached index.", status_code=502
                    )
                index = cached[0]
            else:
                try:
                    decoded = json.loads((result.body or b"").decode("utf-8"))
                    index = RepositoryIndex.model_validate(decoded)
                except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
                    raise AddonError("invalid_repository", "Repository index is invalid.") from exc
                for entry in index.addons:
                    resolve_same_origin(str(repository.url), entry.manifest_url)
                self._write_cache(repository, index, result.etag)
            self._indexes[repository.id] = index
            self._offline[repository.id] = False
            return index
        except AddonError:
            self._offline[repository.id] = True
            if cached:
                self._indexes[repository.id] = cached[0]
                return cached[0]
            raise

    async def refresh(self) -> dict[str, object]:
        results: list[dict[str, object]] = []
        for repository in self.storage.read_repositories().repositories:
            if not repository.enabled:
                continue
            try:
                await self.refresh_one(repository)
                results.append({"repository_id": repository.id, "offline": self._offline.get(repository.id, False)})
            except AddonError as exc:
                results.append({"repository_id": repository.id, "offline": True, "error": exc.as_dict()})
        return {"repositories": results}

    async def add_repository(self, name: str, url: str) -> Repository:
        canonical = canonical_repository_url(url)
        repository = Repository(
            id=custom_repository_id(canonical),
            name=name,
            url=canonical,
            trust=RepositoryTrust.CUSTOM,
            enabled=True,
        )
        state = self.storage.read_repositories()
        if any(str(item.url) == str(repository.url) for item in state.repositories):
            raise AddonError("repository_exists", "Repository is already configured.", status_code=409)
        await self.refresh_one(repository)
        self.storage.write_repositories(state.model_copy(update={"repositories": [*state.repositories, repository]}))
        return repository

    def remove_repository(self, repository_id: str) -> None:
        if repository_id == OFFICIAL_REPOSITORY_ID:
            raise AddonError("official_repository", "The official repository cannot be removed.", status_code=409)
        state = self.storage.read_repositories()
        repository = next((item for item in state.repositories if item.id == repository_id), None)
        if repository is None:
            raise AddonError("repository_not_found", "Repository was not found.", status_code=404)
        installed = self.storage.read_state().installed
        if any(item.repository_id == repository_id for item in installed.values()):
            raise AddonError(
                "repository_in_use", "Remove its installed add-ons before removing this repository.", status_code=409
            )
        remaining = [item for item in state.repositories if item.id != repository_id]
        self.storage.write_repositories(RepositoryState(repositories=remaining))
        self._indexes.pop(repository_id, None)
        self._cache_path(repository_id).unlink(missing_ok=True)

    def repository(self, repository_id: str) -> Repository:
        repository = next(
            (item for item in self.storage.read_repositories().repositories if item.id == repository_id),
            None,
        )
        if repository is None:
            raise AddonError("repository_not_found", "Repository was not found.", status_code=404)
        return repository

    @staticmethod
    def compatible(entry: IndexAddon) -> bool:
        return Version(__version__) in SpecifierSet(entry.blackbone.version)

    def exact_release(self, repository_id: str, addon_id: str, version: str) -> IndexAddon:
        selected_repository = self.repository(repository_id)
        index = self._indexes.get(repository_id)
        if index is None:
            raise AddonError("catalog_unavailable", "Repository catalog is not available.", status_code=503)
        release = next((item for item in index.addons if item.id == addon_id and item.version == version), None)
        if release is None:
            raise AddonError("release_not_found", "The requested add-on version was not found.", status_code=404)
        conflicting_repositories = [
            candidate_id
            for candidate_id, candidate_index in self._indexes.items()
            if candidate_id != repository_id
            and any(item.id == addon_id for item in candidate_index.addons)
            and self.repository(candidate_id).enabled
        ]
        if conflicting_repositories:
            raise AddonError(
                "addon_id_conflict",
                "This add-on ID is published by more than one repository.",
                details={"addon_id": addon_id, "repository_id": selected_repository.id},
                status_code=409,
            )
        return release

    def catalog(self) -> dict[str, object]:
        repositories = {item.id: item for item in self.storage.read_repositories().repositories}
        installed = self.storage.read_state().installed
        grouped: dict[str, list[tuple[Repository, IndexAddon]]] = {}
        for repository_id, index in self._indexes.items():
            repository = repositories.get(repository_id)
            if repository is None or not repository.enabled:
                continue
            for entry in index.addons:
                grouped.setdefault(entry.id, []).append((repository, entry))

        addons: list[dict[str, object]] = []
        for addon_id, candidates in grouped.items():
            compatible = [item for item in candidates if self.compatible(item[1])]
            pool = compatible or candidates
            # Official wins an ID collision; version ordering then selects the latest release.
            pool.sort(
                key=lambda item: (item[0].trust == RepositoryTrust.OFFICIAL, Version(item[1].version)), reverse=True
            )
            repository, release = pool[0]
            current = installed.get(addon_id)
            addons.append(
                {
                    **release.model_dump(mode="json"),
                    "repository_id": repository.id,
                    "repository_name": repository.name,
                    "trust": repository.trust,
                    "compatible": self.compatible(release),
                    "repository_offline": self._offline.get(repository.id, False),
                    "installed_version": current.version if current else None,
                    "installed": current is not None,
                    "enabled": current.enabled if current else False,
                    "update_available": bool(current and Version(release.version) > Version(current.version)),
                    "repository_conflict": len({item[0].id for item in candidates}) > 1,
                }
            )
        return {"addons": sorted(addons, key=lambda item: str(item["name"]).casefold())}
