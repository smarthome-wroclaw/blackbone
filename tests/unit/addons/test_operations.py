from __future__ import annotations

from pathlib import Path

from boneio.addons.models import OperationStage, OperationType
from boneio.addons.operations import OperationStore
from boneio.addons.paths import AddonPaths


def test_unfinished_operation_is_marked_interrupted(tmp_path: Path) -> None:
    store = OperationStore(AddonPaths(tmp_path))
    record = store.create(OperationType.INSTALL, "community.example", version="1.0.0", repository_id="repo")
    store.update(record, OperationStage.DOWNLOADING, "Downloading")

    recovered = OperationStore(AddonPaths(tmp_path)).recover_unfinished()

    assert len(recovered) == 1
    assert recovered[0].stage == OperationStage.INTERRUPTED
    assert recovered[0].completed_at is not None
