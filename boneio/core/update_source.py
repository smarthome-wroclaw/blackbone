"""Validation for one-off software update sources."""

from __future__ import annotations

import platform
import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

UpdateSourceType = Literal["package", "repository"]

_CONTROL_OR_WHITESPACE = re.compile(r"[\x00-\x20\x7f]")


@dataclass(frozen=True)
class CustomUpdateTarget:
    """A validated target passed to pip as one subprocess argument."""

    source_type: UpdateSourceType
    pip_argument: str
    label: str


def resolve_custom_update_target(
    source_type: UpdateSourceType,
    source: str,
    version: str | None = None,
) -> CustomUpdateTarget:
    """Validate and normalize a package requirement or HTTPS Git repository."""
    value = source.strip()
    if not value:
        raise ValueError("Update source is required")

    if source_type == "package":
        if len(value) > 200:
            raise ValueError("Package specification is too long")
        if value.startswith("-") or _CONTROL_OR_WHITESPACE.search(value):
            raise ValueError("Package specification contains unsupported characters")
        try:
            requirement = Requirement(value)
        except InvalidRequirement as exc:
            raise ValueError("Enter a valid Python package requirement") from exc
        if requirement.url or requirement.marker or requirement.extras or requirement.specifier:
            raise ValueError("Enter only the Python package name; versions are selected separately")
        pip_argument = requirement.name
        if version is not None:
            try:
                normalized_version = str(Version(version.strip()))
            except InvalidVersion as exc:
                raise ValueError("Select a valid package version") from exc
            pip_argument = f"{requirement.name}=={normalized_version}"
        return CustomUpdateTarget(
            source_type=source_type,
            pip_argument=pip_argument,
            label=pip_argument,
        )

    if source_type == "repository":
        if version is not None:
            raise ValueError("A package version cannot be combined with a repository")
        if len(value) > 500:
            raise ValueError("Repository URL is too long")
        if _CONTROL_OR_WHITESPACE.search(value):
            raise ValueError("Repository URL must not contain whitespace")

        raw_url = value.removeprefix("git+")
        parsed = urlsplit(raw_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Repository must use an HTTPS URL")
        if parsed.username or parsed.password:
            raise ValueError("Repository URL must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("Repository URL must not contain a query or fragment")
        if parsed.path in ("", "/"):
            raise ValueError("Repository URL must include a repository path")

        return CustomUpdateTarget(
            source_type=source_type,
            pip_argument=f"git+{raw_url}",
            label=raw_url,
        )

    raise ValueError("Unsupported update source type")


def parse_pypi_package_versions(
    payload: dict[str, Any],
    *,
    python_version: str | None = None,
) -> dict[str, Any]:
    """Extract installable, non-yanked releases from a PyPI project response."""
    runtime_version = Version(python_version or platform.python_version())
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    releases = payload.get("releases") if isinstance(payload.get("releases"), dict) else {}
    parsed_releases: dict[str, dict[str, Any]] = {}

    for raw_version, raw_files in releases.items():
        if not isinstance(raw_version, str) or not isinstance(raw_files, list):
            continue
        try:
            parsed_version = Version(raw_version)
        except InvalidVersion:
            continue
        files = []
        for item in raw_files:
            if not isinstance(item, dict) or item.get("yanked", False):
                continue
            requires_python = item.get("requires_python")
            if isinstance(requires_python, str) and requires_python:
                try:
                    if runtime_version not in SpecifierSet(requires_python):
                        continue
                except InvalidSpecifier:
                    continue
            files.append(item)
        if not files:
            continue
        version = str(parsed_version)
        uploaded_at = max(
            (str(item.get("upload_time_iso_8601", "")) for item in files),
            default="",
        )
        parsed_releases[version] = {
            "version": version,
            "prerelease": parsed_version.is_prerelease or parsed_version.is_devrelease,
            "uploaded_at": uploaded_at,
            "parsed": parsed_version,
        }

    ordered = sorted(
        parsed_releases.values(),
        key=lambda item: item["parsed"],
        reverse=True,
    )
    versions = [
        {key: value for key, value in item.items() if key != "parsed"}
        for item in ordered[:50]
    ]
    latest_stable = next(
        (item["version"] for item in versions if not item["prerelease"]),
        None,
    )
    return {
        "package": str(info.get("name", "")),
        "summary": str(info.get("summary", "")),
        "project_url": str(info.get("project_url", "")),
        "latest": versions[0]["version"] if versions else None,
        "latest_stable": latest_stable,
        "versions": versions,
    }
