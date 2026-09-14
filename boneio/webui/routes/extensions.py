"""API for lifecycle operations of reviewed container extensions."""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from boneio.extensions.manifest import ExtensionManifest
from boneio.extensions.runtime import ContainerExtensionRuntime, ExtensionRuntimeError
from boneio.webui.routes.config_core import _get_app_state

router = APIRouter(prefix="/api/extensions", tags=["extensions"])


class StartExtensionRequest(BaseModel):
    manifest: ExtensionManifest
    approved_permissions: set[str]


def _runtime() -> ContainerExtensionRuntime:
    return ContainerExtensionRuntime(Path(_get_app_state().yaml_config_file).parent / "extensions")


@router.post("/start")
async def start_extension(request: StartExtensionRequest):
    try:
        return _runtime().start(request.manifest, request.approved_permissions)
    except ExtensionRuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{extension_id}/stop")
async def stop_extension(extension_id: str):
    return _runtime().stop(extension_id)


@router.get("/{extension_id}")
async def extension_status(extension_id: str):
    return _runtime().status(extension_id)


@router.get("/{extension_id}/logs")
async def extension_logs(extension_id: str, tail: int = 200):
    return {"logs": _runtime().logs(extension_id, tail)}
