from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.modules.setdefault("gpiod", MagicMock())
sys.modules.setdefault("gpiod.line", MagicMock())
sys.modules.setdefault("smbus2", MagicMock())

from boneio.webui.app import app as production_app  # noqa: E402
from boneio.webui.routes.addons import router  # noqa: E402


def _production_route_paths() -> set[str]:
    paths: set[str] = set()
    for route in production_app.routes:
        included = getattr(route, "original_router", None)
        candidates = included.routes if included is not None else [route]
        paths.update(item.path for item in candidates if hasattr(item, "path"))
    return paths


def test_production_routes_gate_container_extensions() -> None:
    paths = _production_route_paths()
    assert "/api/addons" in paths
    assert "/api/extensions/start" not in paths


def test_feature_is_disabled_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("BONEIO_ADDONS", raising=False)
    app = FastAPI()
    app.include_router(router)
    app.state.yaml_config_file = str(tmp_path / "config.yaml")

    response = TestClient(app).get("/api/addons")

    assert response.status_code == 404
    assert response.json()["code"] == "feature_disabled"


def test_mutations_require_dashboard_credentials(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BONEIO_ADDONS", "true")
    (tmp_path / "config.yaml").write_text("boneio:\n  name: test\n")
    app = FastAPI()
    app.include_router(router)
    app.state.yaml_config_file = str(tmp_path / "config.yaml")
    app.state.auth_config = {}

    response = TestClient(app).post("/api/addons/refresh")

    assert response.status_code == 428
    assert response.json()["code"] == "authentication_setup_required"


def test_invalid_request_uses_stable_error_envelope(monkeypatch) -> None:
    monkeypatch.setenv("BONEIO_ADDONS", "true")
    app = FastAPI()
    app.include_router(router)

    response = TestClient(app).post("/api/addons/repositories", json={"url": "https://example.com/index.json"})

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert "input" not in str(response.json())
