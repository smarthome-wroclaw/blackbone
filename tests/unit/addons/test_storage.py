from __future__ import annotations

import json
from pathlib import Path

import pytest

from boneio.addons.errors import AddonError
from boneio.addons.models import Repository, RepositoryState, RepositoryTrust
from boneio.addons.paths import AddonPaths
from boneio.addons.storage import AddonStorage, MutationLock


def test_state_write_is_atomic_when_replace_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = AddonPaths(tmp_path)
    storage = AddonStorage(paths)
    initial = RepositoryState(
        repositories=[
            Repository(
                id="official", name="Official", url="https://example.com/index.json", trust=RepositoryTrust.OFFICIAL
            )
        ]
    )
    storage.write_repositories(initial)
    before = paths.repositories.read_bytes()

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("simulated power-loss boundary")

    monkeypatch.setattr("boneio.addons.storage.os.replace", fail_replace)
    with pytest.raises(OSError):
        storage.write_repositories(RepositoryState())
    assert paths.repositories.read_bytes() == before
    assert json.loads(before)["repositories"][0]["id"] == "official"


def test_second_mutation_lock_fails_without_blocking(tmp_path: Path) -> None:
    first = MutationLock(tmp_path / "lock")
    second = MutationLock(tmp_path / "lock")
    first.acquire()
    try:
        with pytest.raises(Exception, match="already running"):
            second.acquire()
    finally:
        first.release()


def test_corrupt_installed_state_fails_closed(tmp_path: Path) -> None:
    paths = AddonPaths(tmp_path)
    storage = AddonStorage(paths)
    paths.state.write_text("{not-json", encoding="utf-8")

    with pytest.raises(AddonError) as error:
        storage.read_state()

    assert error.value.code == "installed_state_corrupt"
