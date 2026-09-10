"""Authenticated API for safe, declarative BlackBone add-ons."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from boneio.addons import AddonError, AddonService
from boneio.webui.routes.config_core import _get_app_state

router = APIRouter(prefix="/api/addons", tags=["addons"])


class RepositoryRequest(BaseModel):
    url: HttpUrl


class InstallRequest(BaseModel):
    repository: HttpUrl
    version: str | None = None


def _service() -> AddonService:
    return AddonService(Path(_get_app_state().yaml_config_file).parent)


def _error(error: AddonError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


@router.get("")
async def get_addons():
    """Return installed add-ons and configured repositories."""
    return _service().list_state()


@router.get("/catalog")
async def get_catalog():
    """Fetch enabled registries and return compatible add-on metadata."""
    try:
        return _service().catalog()
    except AddonError as exc:
        raise _error(exc) from exc


@router.post("/repositories", status_code=201)
async def add_repository(request: RepositoryRequest):
    try:
        return _service().add_repository(str(request.url))
    except AddonError as exc:
        raise _error(exc) from exc


@router.delete("/repositories/{repository_id}")
async def remove_repository(repository_id: str):
    try:
        _service().remove_repository(repository_id)
        return {"removed": True}
    except AddonError as exc:
        raise _error(exc) from exc


@router.post("/{addon_id}/install")
async def install_addon(addon_id: str, request: InstallRequest):
    try:
        return _service().install(addon_id, str(request.repository), request.version)
    except AddonError as exc:
        raise _error(exc) from exc


@router.post("/{addon_id}/update")
async def update_addon(addon_id: str, request: InstallRequest):
    try:
        return _service().install(addon_id, str(request.repository), request.version)
    except AddonError as exc:
        raise _error(exc) from exc


@router.delete("/{addon_id}")
async def remove_addon(addon_id: str):
    try:
        return _service().remove(addon_id)
    except AddonError as exc:
        raise _error(exc) from exc
