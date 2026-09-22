"""Drop policy-owned paths out of an upstream patch before git applies it."""

from __future__ import annotations

from dataclasses import dataclass, field

from .policy import PathClass, Policy

_HEADER = "diff --git "

#: Classes whose sections never reach git; each is handled by a later stage.
_DROPPED_CLASSES = frozenset(
    {
        PathClass.FORK_OWNED,
        PathClass.FORK_DELETED,
        PathClass.UPSTREAM_DELETED,
        PathClass.UNION,
        PathClass.REGENERATE,
        PathClass.MANIFEST,
    }
)


@dataclass
class PatchSection:
    """One file's slice of a patch, applied on its own."""

    primary: str
    paths: set[str]
    text: str


@dataclass
class FilterResult:
    patch: str
    dropped: dict[str, PathClass] = field(default_factory=dict)
    sections: list[PatchSection] = field(default_factory=list)


def _split_sections(patch: str) -> list[list[str]]:
    sections: list[list[str]] = []
    current: list[str] = []
    for line in patch.splitlines(keepends=True):
        if line.startswith(_HEADER) and current:
            sections.append(current)
            current = []
        current.append(line)
    if current:
        sections.append(current)
    return sections


def _paths_in(section: list[str]) -> set[str]:
    """Every path a section touches, so a rename is judged on both of its ends."""
    paths: set[str] = set()
    for line in section:
        stripped = line.rstrip("\n")
        if stripped.startswith("--- a/"):
            paths.add(stripped[len("--- a/") :])
        elif stripped.startswith("+++ b/"):
            paths.add(stripped[len("+++ b/") :])
        elif stripped.startswith("rename from "):
            paths.add(stripped[len("rename from ") :])
        elif stripped.startswith("rename to "):
            paths.add(stripped[len("rename to ") :])

    if not paths and section and section[0].startswith(_HEADER):
        # A binary or mode-only section carries no ---/+++ lines, so the
        # header is the only source. Paths containing " b/" would defeat this,
        # but git quotes those.
        rest = section[0].rstrip("\n")[len(_HEADER) :]
        if rest.startswith("a/") and " b/" in rest:
            left, _, right = rest.partition(" b/")
            paths.add(left[len("a/") :])
            paths.add(right)
    return paths


def _primary_path(section: list[str], paths: set[str]) -> str:
    for line in section:
        stripped = line.rstrip("\n")
        if stripped.startswith("+++ b/"):
            return stripped[len("+++ b/") :]
    return sorted(paths)[0] if paths else ""


def filter_patch(patch: str, policy: Policy) -> FilterResult:
    """Return the patch with policy-owned sections removed, and what was removed.

    Sections are kept individually as well as joined, so the caller can apply
    them one at a time — a single unappliable file must not roll back the rest.
    """
    kept: list[str] = []
    dropped: dict[str, PathClass] = {}
    sections: list[PatchSection] = []

    for section in _split_sections(patch):
        verdict: PathClass | None = None
        paths = _paths_in(section)
        for path in sorted(paths):
            path_class = policy.classify(path)
            if path_class in _DROPPED_CLASSES:
                dropped[path] = path_class
                verdict = path_class
        if verdict is None:
            kept.extend(section)
            sections.append(
                PatchSection(
                    primary=_primary_path(section, paths),
                    paths=paths,
                    text="".join(section),
                )
            )

    return FilterResult(patch="".join(kept), dropped=dropped, sections=sections)
