"""Durable JSON storage and the global add-on mutation lock."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
import threading
from pathlib import Path

from pydantic import BaseModel, ValidationError

from boneio.addons.errors import AddonError
from boneio.addons.models import InstalledState, RepositoryState
from boneio.addons.paths import AddonPaths


def atomic_write_bytes(path: Path, payload: bytes, *, mode: int = 0o640) -> None:
    """Replace *path* only after its complete content is durable."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    except Exception:
        with contextlib.suppress(OSError):
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise


def fsync_directory(path: Path) -> None:
    if os.name != "posix":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_model(path: Path, model: BaseModel) -> None:
    payload = json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True).encode("utf-8") + b"\n"
    atomic_write_bytes(path, payload)


def read_model[ModelT: BaseModel](path: Path, model_type: type[ModelT], default: ModelT) -> ModelT:
    if not path.exists():
        return default
    with path.open("rb") as handle:
        return model_type.model_validate_json(handle.read())


class MutationLock:
    """One process/thread-safe filesystem lock for all add-on mutations."""

    _thread_lock = threading.Lock()

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None

    def acquire(self, *, blocking: bool = False) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        if not self._thread_lock.acquire(blocking=blocking):
            raise AddonError("mutation_in_progress", "Another add-on operation is already running.", status_code=409)
        self._handle = self.path.open("a+b")
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(self._handle.fileno(), flags)
        except BlockingIOError as exc:
            self._handle.close()
            self._handle = None
            self._thread_lock.release()
            raise AddonError(
                "mutation_in_progress", "Another add-on operation is already running.", status_code=409
            ) from exc

    def release(self) -> None:
        if self._handle is None:
            return
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None
        self._thread_lock.release()

    def __enter__(self) -> MutationLock:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
        self.release()


class AddonStorage:
    def __init__(self, paths: AddonPaths) -> None:
        self.paths = paths
        self.paths.ensure()
        self.mutation_lock = MutationLock(paths.lock)

    def read_repositories(self) -> RepositoryState:
        try:
            return read_model(self.paths.repositories, RepositoryState, RepositoryState())
        except (OSError, ValidationError) as exc:
            raise AddonError(
                "repository_state_corrupt", "Add-on repository state is invalid.", status_code=503
            ) from exc

    def write_repositories(self, value: RepositoryState) -> None:
        atomic_write_model(self.paths.repositories, value)

    def read_state(self) -> InstalledState:
        try:
            return read_model(self.paths.state, InstalledState, InstalledState())
        except (OSError, ValidationError) as exc:
            raise AddonError("installed_state_corrupt", "Installed add-on state is invalid.", status_code=503) from exc

    def write_state(self, value: InstalledState) -> None:
        atomic_write_model(self.paths.state, value)
