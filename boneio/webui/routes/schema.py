"""Serve generated schemas with the live Modbus model enum."""
from __future__ import annotations
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter()
SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"

def _patch_model_enums(node, models: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "model" and isinstance(value, dict) and isinstance(value.get("enum"), list):
                value["enum"] = models
            _patch_model_enums(value, models)
    elif isinstance(node, list):
        for item in node:
            _patch_model_enums(item, models)

@router.get("/schema/{filename}")
async def serve_schema(filename: str):
    path = SCHEMA_DIR / filename
    if filename != path.name or not filename.endswith(".schema.json") or not path.is_file():
        raise HTTPException(404, f"Schema '{filename}' not found")
    with open(path, encoding="utf-8") as file:
        schema = json.load(file)
    from boneio.modbus import device_registry
    _patch_model_enums(schema, sorted(ref.key for ref in device_registry.list_models()))
    return JSONResponse(schema, headers={"Cache-Control": "no-cache"})
