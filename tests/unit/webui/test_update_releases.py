"""Tests for release discovery in the WebUI update routes.

The routes module is loaded directly via importlib so the test does not pull
in the hardware-only ``boneio`` package tree (gpiod, smbus2, ...).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _load_routes_update_module():
    """Load boneio/webui/routes/update.py with its boneio imports stubbed."""
    stub_pkgs = [
        "boneio",
        "boneio.core",
        "boneio.core.config",
        "boneio.core.config.yaml_util",
        "boneio.core.update_source",
        "boneio.version",
        "boneio.webui",
        "boneio.webui.services",
        "boneio.webui.services.logs",
    ]

    saved: dict[str, types.ModuleType | None] = {p: sys.modules.get(p) for p in stub_pkgs}

    try:
        for pkg in stub_pkgs:
            mod = types.ModuleType(pkg)
            mod.__path__ = []
            mod.__package__ = pkg
            sys.modules[pkg] = mod

        yaml_util = sys.modules["boneio.core.config.yaml_util"]
        yaml_util.load_config_from_file = MagicMock()
        yaml_util.load_yaml_file = MagicMock()
        yaml_util.normalize_board_name = MagicMock()

        update_source = sys.modules["boneio.core.update_source"]
        update_source.parse_pypi_package_versions = MagicMock()
        update_source.resolve_custom_update_target = MagicMock()

        sys.modules["boneio.webui.services.logs"].is_running_as_service = MagicMock(return_value=True)
        sys.modules["boneio.version"].__version__ = "0.1.2"

        path = Path(__file__).resolve().parents[3] / "boneio" / "webui" / "routes" / "update.py"
        spec = importlib.util.spec_from_file_location("_test_routes_update_module", str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    finally:
        for pkg in stub_pkgs:
            original = saved[pkg]
            if original is None:
                sys.modules.pop(pkg, None)
            else:
                sys.modules[pkg] = original


_routes_update = _load_routes_update_module()


def _fake_requests(response) -> types.ModuleType:
    """Build a stand-in ``requests`` module returning a fixed response."""
    module = types.ModuleType("requests")
    module.get = MagicMock(return_value=response)
    return module


def _ok_response(payload: list[dict]) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload
    return response


def _fork_releases() -> list[dict]:
    """Releases as published by smarthome-wroclaw/blackbone (0.x tags only)."""
    base = "https://github.com/smarthome-wroclaw/blackbone/releases/tag"
    return [
        {
            "tag_name": "v0.1.3",
            "prerelease": False,
            "html_url": f"{base}/v0.1.3",
            "published_at": "2026-09-09T23:30:26Z",
            "body": "Newest fork release",
        },
        {
            "tag_name": "v0.1.2",
            "prerelease": False,
            "html_url": f"{base}/v0.1.2",
            "published_at": "2026-09-07T23:13:03Z",
            "body": "Older fork release",
        },
    ]


@pytest.fixture(autouse=True)
def _clear_release_cache():
    """The module caches releases for 15 minutes — reset around every test."""
    _routes_update._GITHUB_RELEASES_CACHE["data"] = None
    _routes_update._GITHUB_RELEASES_CACHE["fetched_at"] = 0.0
    yield
    _routes_update._GITHUB_RELEASES_CACHE["data"] = None
    _routes_update._GITHUB_RELEASES_CACHE["fetched_at"] = 0.0


class TestReleaseSource:
    """Releases must come from the fork, not from upstream boneIO."""

    def test_default_repo_is_the_fork(self, monkeypatch):
        """_fetch_github_releases queries smarthome-wroclaw/blackbone by default."""
        requests_stub = _fake_requests(_ok_response([]))
        monkeypatch.setitem(sys.modules, "requests", requests_stub)

        releases, error = _routes_update._fetch_github_releases()

        assert error is None
        assert releases == []
        requested_url = requests_stub.get.call_args[0][0]
        assert requested_url == "https://api.github.com/repos/smarthome-wroclaw/blackbone/releases"

    def test_explicit_repo_still_honoured(self, monkeypatch):
        """An explicit repo argument overrides the default."""
        requests_stub = _fake_requests(_ok_response([]))
        monkeypatch.setitem(sys.modules, "requests", requests_stub)

        _routes_update._fetch_github_releases(repo="someone/else")

        assert requests_stub.get.call_args[0][0] == "https://api.github.com/repos/someone/else/releases"


class TestCheckUpdateWithForkReleases:
    """BlackBone tags start at v0.1.0 and must survive the version filter."""

    async def test_v0_releases_are_not_filtered_out(self, monkeypatch):
        """check_update lists v0.x releases and picks the newest as latest stable."""
        monkeypatch.setitem(sys.modules, "requests", _fake_requests(_ok_response(_fork_releases())))
        monkeypatch.setattr(_routes_update, "__version__", "0.1.2")

        result = await _routes_update.check_update()

        assert result["status"] == "success"
        assert result["current_version"] == "0.1.2"
        assert result["latest_stable"] == "0.1.3"
        assert result["latest_version"] == "0.1.3"
        assert result["update_available"] is True
        assert [v["version"] for v in result["available_versions"]] == ["0.1.3", "0.1.2"]
