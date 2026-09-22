"""Persisted progress records for add-on lifecycle operations."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from boneio.addons.errors import AddonError
from boneio.addons.models import OperationRecord, OperationStage, OperationType
from boneio.addons.paths import AddonPaths
from boneio.addons.storage import atomic_write_model, read_model

FINAL_STAGES = {OperationStage.SUCCEEDED, OperationStage.FAILED, OperationStage.INTERRUPTED}


class OperationStore:
    def __init__(self, paths: AddonPaths, *, history_limit: int = 100) -> None:
        self.paths = paths
        self.history_limit = history_limit
        paths.ensure()

    def create(
        self,
        operation_type: OperationType,
        addon_id: str,
        *,
        version: str | None = None,
        repository_id: str | None = None,
    ) -> OperationRecord:
        record = OperationRecord(
            id=str(uuid4()),
            type=operation_type,
            addon_id=addon_id,
            version=version,
            repository_id=repository_id,
            started_at=datetime.now(UTC),
        )
        self.save(record)
        self.prune()
        return record

    def path_for(self, operation_id: str) -> Path:
        try:
            uuid4_value = __import__("uuid").UUID(operation_id)
        except (ValueError, AttributeError) as exc:
            raise AddonError("operation_not_found", "Operation was not found.", status_code=404) from exc
        return self.paths.operations / f"{uuid4_value}.json"

    def save(self, record: OperationRecord) -> None:
        atomic_write_model(self.path_for(record.id), record)

    def get(self, operation_id: str) -> OperationRecord:
        path = self.path_for(operation_id)
        if not path.exists():
            raise AddonError("operation_not_found", "Operation was not found.", status_code=404)
        try:
            return read_model(path, OperationRecord, None)  # type: ignore[arg-type]
        except (OSError, ValidationError) as exc:
            raise AddonError("operation_corrupt", "Operation record is invalid.", status_code=503) from exc

    def update(
        self, record: OperationRecord, stage: OperationStage, message: str, **changes: object
    ) -> OperationRecord:
        values = {"stage": stage, "message": message, **changes}
        if stage in FINAL_STAGES:
            values["completed_at"] = datetime.now(UTC)
        updated = OperationRecord.model_validate({**record.model_dump(), **values})
        self.save(updated)
        return updated

    def recover_unfinished(self) -> list[OperationRecord]:
        recovered: list[OperationRecord] = []
        for path in sorted(self.paths.operations.glob("*.json")):
            record = read_model(path, OperationRecord, None)  # type: ignore[arg-type]
            if record.stage not in FINAL_STAGES:
                record = self.update(
                    record,
                    OperationStage.INTERRUPTED,
                    "Operation was interrupted by a controller restart.",
                )
                recovered.append(record)
        return recovered

    def list(self, *, addon_id: str | None = None) -> list[OperationRecord]:
        try:
            records = [
                read_model(path, OperationRecord, None)  # type: ignore[arg-type]
                for path in self.paths.operations.glob("*.json")
            ]
        except (OSError, ValidationError) as exc:
            raise AddonError("operation_store_corrupt", "Operation history is invalid.", status_code=503) from exc
        if addon_id is not None:
            records = [record for record in records if record.addon_id == addon_id]
        return sorted(records, key=lambda item: item.started_at, reverse=True)

    def prune(self) -> None:
        records = self.list()
        for record in records[self.history_limit :]:
            if record.stage in FINAL_STAGES and not record.snapshot_path:
                self.path_for(record.id).unlink(missing_ok=True)
