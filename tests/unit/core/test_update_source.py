"""Tests for validated one-off update sources."""

import pytest

from boneio.core.update_source import parse_pypi_package_versions, resolve_custom_update_target


def test_accepts_python_package_name_and_selected_version():
    target = resolve_custom_update_target("package", "  blackbone  ", version="1.6.0")

    assert target.pip_argument == "blackbone==1.6.0"
    assert target.label == "blackbone==1.6.0"


@pytest.mark.parametrize(
    "source",
    [
        "--extra-index-url=https://example.com",
        "blackbone==1.6.0",
        "blackbone @ https://example.com/package.whl",
        'blackbone; python_version > "3.12"',
        "boneio fork",
    ],
)
def test_rejects_unsupported_package_syntax(source: str):
    with pytest.raises(ValueError):
        resolve_custom_update_target("package", source)


def test_normalizes_https_git_repository():
    target = resolve_custom_update_target(
        "repository",
        "https://github.com/example/blackbone.git@stable",
    )

    assert target.pip_argument == "git+https://github.com/example/blackbone.git@stable"
    assert target.label == "https://github.com/example/blackbone.git@stable"


def test_accepts_existing_git_https_prefix():
    target = resolve_custom_update_target(
        "repository",
        "git+https://git.example.com/team/boneio.git",
    )

    assert target.pip_argument == "git+https://git.example.com/team/boneio.git"


@pytest.mark.parametrize(
    "source",
    [
        "http://github.com/example/boneio.git",
        "git+ssh://git@github.com/example/boneio.git",
        "https://user:secret@example.com/boneio.git",
        "https://example.com/boneio.git?token=secret",
        "https://example.com/boneio.git#subdirectory=app",
        "https://example.com",
    ],
)
def test_rejects_unsafe_or_incomplete_repository_urls(source: str):
    with pytest.raises(ValueError):
        resolve_custom_update_target("repository", source)


def test_sorts_pypi_versions_and_ignores_yanked_releases():
    package = parse_pypi_package_versions({
        "info": {
            "name": "blackbone",
            "summary": "Alternative controller package",
            "project_url": "https://pypi.org/project/blackbone/",
        },
        "releases": {
            "1.9.0": [{"yanked": False, "upload_time_iso_8601": "2026-07-01T10:00:00Z"}],
            "2.0.0.dev1": [{"yanked": False, "upload_time_iso_8601": "2026-08-01T10:00:00Z"}],
            "1.8.0": [{"yanked": True, "upload_time_iso_8601": "2026-06-01T10:00:00Z"}],
            "3.0.0": [{"yanked": False, "requires_python": ">=3.14"}],
            "not-a-version": [{"yanked": False}],
        },
    }, python_version="3.13.2")

    assert package["package"] == "blackbone"
    assert package["latest"] == "2.0.0.dev1"
    assert package["latest_stable"] == "1.9.0"
    assert package["versions"] == [
        {
            "version": "2.0.0.dev1",
            "prerelease": True,
            "uploaded_at": "2026-08-01T10:00:00Z",
        },
        {
            "version": "1.9.0",
            "prerelease": False,
            "uploaded_at": "2026-07-01T10:00:00Z",
        },
    ]
