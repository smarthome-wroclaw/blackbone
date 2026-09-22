from __future__ import annotations

import json
from pathlib import Path

import pytest

from boneio.addons.errors import AddonError
from boneio.addons.models import Repository, RepositoryState, RepositoryTrust
from boneio.addons.network import FetchResult
from boneio.addons.paths import AddonPaths
from boneio.addons.registry import RegistryClient
from boneio.addons.storage import AddonStorage


class SequenceFetcher:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.fail = False

    async def fetch(self, url: str, *, limit: int, etag: str | None = None) -> FetchResult:
        if self.fail:
            raise AddonError("repository_unavailable", "offline", status_code=502)
        return FetchResult(self.payload, '"v1"')


@pytest.mark.asyncio
async def test_last_known_good_catalog_survives_offline_refresh(tmp_path: Path) -> None:
    paths = AddonPaths(tmp_path)
    storage = AddonStorage(paths)
    repository = Repository(
        id="custom-example",
        name="Example",
        url="https://example.com/index.json",
        trust=RepositoryTrust.CUSTOM,
    )
    storage.write_repositories(RepositoryState(repositories=[repository]))
    index = json.dumps(
        {
            "schema_version": 1,
            "addons": [
                {
                    "id": "community.example",
                    "name": "Example",
                    "version": "1.0.0",
                    "type": "modbus_device_pack",
                    "blackbone": {"version": ">=0.1.0,<1.0.0"},
                    "manifest_url": "packs/example/addon.yaml",
                    "manifest_sha256": "a" * 64,
                }
            ],
        }
    ).encode()
    fetcher = SequenceFetcher(index)
    registry = RegistryClient(paths, storage, fetcher)  # type: ignore[arg-type]
    await registry.refresh_one(registry.repository("custom-example"))
    fetcher.fail = True

    await registry.refresh_one(registry.repository("custom-example"))

    catalog = registry.catalog()["addons"]
    assert len(catalog) == 1
    assert catalog[0]["repository_offline"] is True
