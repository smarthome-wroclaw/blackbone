"""HTTP adapter for the declarative add-on lifecycle service."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from boneio.addons.errors import AddonError
from boneio.addons.models import (
    ConfirmRequest,
    OperationType,
    PreviewRequest,
    RemoveRequest,
    RepositoryCreateRequest,
    RollbackRequest,
)
from boneio.addons.service import AddonService


class AddonRoute(APIRoute):
    """Keep request validation errors inside the stable add-on error envelope."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original(request)
            except RequestValidationError as exc:
                details = {
                    "errors": [
                        {
                            "location": ".".join(str(part) for part in error["loc"]),
                            "message": error["msg"],
                            "type": error["type"],
                        }
                        for error in exc.errors()
                    ]
                }
                return JSONResponse(
                    status_code=422,
                    content={"code": "invalid_request", "message": "Request data is invalid.", "details": details},
                )

        return handler


router = APIRouter(prefix="/api/addons", tags=["addons"], route_class=AddonRoute)
_ENABLED_VALUES = {"1", "true", "yes", "on"}


def addons_enabled() -> bool:
    return os.environ.get("BONEIO_ADDONS", "").lower() in _ENABLED_VALUES


def _service(request: Request) -> AddonService:
    if not addons_enabled():
        raise AddonError("feature_disabled", "Add-ons are not enabled on this controller.", status_code=404)
    service = getattr(request.app.state, "addon_service", None)
    if service is None:
        config_file = getattr(request.app.state, "yaml_config_file", None)
        if not config_file:
            raise AddonError("service_unavailable", "Add-on service is not initialized.", status_code=503)
        secret = getattr(request.app.state, "addon_token_secret", None)
        service = AddonService(config_file, manager=getattr(request.app.state, "manager", None), token_secret=secret)
        request.app.state.addon_service = service
    return service


def _require_mutation_auth(request: Request) -> None:
    auth = getattr(request.app.state, "auth_config", {}) or {}
    if not auth.get("username") or not auth.get("password"):
        raise AddonError(
            "authentication_setup_required",
            "Configure dashboard credentials before changing add-ons.",
            status_code=428,
        )


def _start(request: Request, operation_id: str, awaitable: Awaitable[None]) -> dict[str, str]:
    task = asyncio.create_task(awaitable, name=f"addon-operation-{operation_id}")
    tasks: set[asyncio.Task[None]] = getattr(request.app.state, "addon_tasks", set())
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    request.app.state.addon_tasks = tasks
    return {"operation_id": operation_id}


def _error(exc: AddonError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.as_dict())


@router.get("")
async def get_addons(request: Request):
    try:
        return _service(request).state()
    except AddonError as exc:
        return _error(exc)


@router.get("/catalog")
async def get_catalog(request: Request):
    try:
        return _service(request).registry.catalog()
    except AddonError as exc:
        return _error(exc)


@router.post("/refresh")
async def refresh_catalog(request: Request):
    try:
        _require_mutation_auth(request)
        return await _service(request).refresh()
    except AddonError as exc:
        return _error(exc)


@router.post("/repositories", status_code=201)
async def add_repository(body: RepositoryCreateRequest, request: Request):
    try:
        _require_mutation_auth(request)
        return await _service(request).add_repository(body)
    except AddonError as exc:
        return _error(exc)


@router.delete("/repositories/{repository_id}", status_code=204)
async def remove_repository(repository_id: str, request: Request):
    try:
        _require_mutation_auth(request)
        _service(request).remove_repository(repository_id)
        return None
    except AddonError as exc:
        return _error(exc)


@router.post("/{addon_id}/preview")
async def preview(addon_id: str, body: PreviewRequest, request: Request):
    try:
        _require_mutation_auth(request)
        return await _service(request).preview(addon_id, body.repository_id, body.version, body.action)
    except AddonError as exc:
        return _error(exc)


@router.post("/{addon_id}/install", status_code=202)
async def install(addon_id: str, body: ConfirmRequest, request: Request):
    try:
        _require_mutation_auth(request)
        record, awaitable = _service(request).queue_confirmed(addon_id, body.confirmation_token, OperationType.INSTALL)
        return _start(request, record.id, awaitable)
    except AddonError as exc:
        return _error(exc)


@router.post("/{addon_id}/update", status_code=202)
async def update(addon_id: str, body: ConfirmRequest, request: Request):
    try:
        _require_mutation_auth(request)
        record, awaitable = _service(request).queue_confirmed(addon_id, body.confirmation_token, OperationType.UPDATE)
        return _start(request, record.id, awaitable)
    except AddonError as exc:
        return _error(exc)


@router.post("/{addon_id}/enable", status_code=202)
async def enable(addon_id: str, request: Request):
    try:
        _require_mutation_auth(request)
        record, awaitable = _service(request).queue_toggle(addon_id, enabled=True)
        return _start(request, record.id, awaitable)
    except AddonError as exc:
        return _error(exc)


@router.post("/{addon_id}/disable", status_code=202)
async def disable(addon_id: str, request: Request):
    try:
        _require_mutation_auth(request)
        record, awaitable = _service(request).queue_toggle(addon_id, enabled=False)
        return _start(request, record.id, awaitable)
    except AddonError as exc:
        return _error(exc)


@router.delete("/{addon_id}", status_code=202)
async def remove(addon_id: str, body: RemoveRequest, request: Request):
    try:
        _require_mutation_auth(request)
        if body.confirmation != addon_id:
            raise AddonError("confirmation_mismatch", "Type the add-on ID to confirm removal.", status_code=409)
        record, awaitable = _service(request).queue_remove(addon_id)
        return _start(request, record.id, awaitable)
    except AddonError as exc:
        return _error(exc)


@router.get("/operations/{operation_id}")
async def operation(operation_id: str, request: Request):
    try:
        return _service(request).operations.get(operation_id)
    except AddonError as exc:
        return _error(exc)


@router.get("/{addon_id}/snapshots")
async def snapshots(addon_id: str, request: Request):
    try:
        return {"snapshots": _service(request).snapshots.list(addon_id)}
    except AddonError as exc:
        return _error(exc)


@router.post("/{addon_id}/rollback", status_code=202)
async def rollback(addon_id: str, body: RollbackRequest, request: Request):
    try:
        _require_mutation_auth(request)
        record, awaitable = _service(request).queue_rollback(addon_id, body.snapshot_id)
        return _start(request, record.id, awaitable)
    except AddonError as exc:
        return _error(exc)
