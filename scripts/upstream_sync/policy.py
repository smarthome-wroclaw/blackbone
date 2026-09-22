"""The declarative path policy the sync workflow applies to an upstream batch."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import yaml

DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parents[2] / ".github" / "upstream-sync-policy.yml"
)


class PolicyError(Exception):
    """The policy file is malformed, or claims one path for two classes."""


class PathClass(Enum):
    FORK_OWNED = "fork_owned"
    FORK_DELETED = "fork_deleted"
    UPSTREAM_DELETED = "upstream_deleted"
    UNION = "union"
    REGENERATE = "regenerate"
    MANIFEST = "manifests"
    MERGE = "merge"


#: Classes whose entries are bare path globs.
_GLOB_CLASSES = (
    PathClass.FORK_OWNED,
    PathClass.FORK_DELETED,
    PathClass.UPSTREAM_DELETED,
    PathClass.UNION,
)
#: Classes whose entries are mappings carrying a ``path`` plus extra fields.
_MAPPING_CLASSES = (PathClass.REGENERATE, PathClass.MANIFEST)


def _translate(pattern: str) -> re.Pattern[str]:
    """Compile a path glob where ``*`` stays within a segment and ``**`` does not."""
    out: list[str] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "*":
            if pattern[i : i + 2] == "**":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(char))
        i += 1
    return re.compile("^" + "".join(out) + "$")


@dataclass
class Policy:
    patterns: list[tuple[re.Pattern[str], PathClass, str]] = field(default_factory=list)
    _regenerate: list[tuple[str, str]] = field(default_factory=list)
    _identity_keys: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict) -> "Policy":
        known = {member.value: member for member in PathClass if member is not PathClass.MERGE}
        unknown = sorted(set(raw) - set(known))
        if unknown:
            raise PolicyError(f"unknown policy class(es): {', '.join(unknown)}")

        policy = cls()
        claimed: dict[str, str] = {}

        for name, member in known.items():
            entries = raw.get(name) or []
            for entry in entries:
                if member in _MAPPING_CLASSES:
                    if not isinstance(entry, dict) or "path" not in entry:
                        raise PolicyError(f"{name} entries need a 'path': {entry!r}")
                    path = entry["path"]
                    if member is PathClass.REGENERATE:
                        if "command" not in entry:
                            raise PolicyError(f"{path} needs a 'command' to rebuild it")
                        policy._regenerate.append((path, entry["command"]))
                    else:
                        policy._identity_keys[path] = list(entry.get("identity_keys", []))
                else:
                    if not isinstance(entry, str):
                        raise PolicyError(f"{name} entries must be strings: {entry!r}")
                    path = entry

                if path in claimed:
                    raise PolicyError(
                        f"{path} is claimed by both {claimed[path]} and {name}"
                    )
                claimed[path] = name
                policy.patterns.append((_translate(path), member, path))

        return policy

    @classmethod
    def load(cls, path: Path) -> "Policy":
        return cls.from_dict(yaml.safe_load(path.read_text()) or {})

    @classmethod
    def load_default(cls) -> "Policy":
        return cls.load(DEFAULT_POLICY_PATH)

    def classify(self, path: str) -> PathClass:
        found: list[tuple[PathClass, str]] = [
            (member, source)
            for compiled, member, source in self.patterns
            if compiled.match(path)
        ]
        if not found:
            return PathClass.MERGE
        distinct = {member for member, _ in found}
        if len(distinct) > 1:
            claims = ", ".join(f"{source} ({member.value})" for member, source in found)
            raise PolicyError(f"{path} is claimed by several classes: {claims}")
        return found[0][0]

    def regenerate_commands(self) -> list[tuple[str, str]]:
        return list(self._regenerate)

    def identity_keys(self, path: str) -> list[str]:
        return list(self._identity_keys.get(path, []))
