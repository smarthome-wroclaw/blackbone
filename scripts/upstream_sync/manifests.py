"""Semantic three-way merge of dependency manifests.

Git resolves a pinned-dependency array by hunk, so contiguous pin lines
conflict en bloc even where both sides made the identical bump. This module
merges per dependency instead, keeping upstream's document (and its comments
and structure) and re-applying the fork's identity keys on top.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from .versions import resolve_pin


@dataclass(frozen=True)
class Decision:
    """How one dependency was resolved, for the PR body."""

    name: str
    value: str | None
    reason: str
    needs_review: bool


@dataclass
class ManifestMerge:
    text: str
    decisions: list[Decision] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return any(decision.needs_review for decision in self.decisions)


def _index(deps: list[str]) -> dict[str, str]:
    """Map canonical distribution name to the requirement string that declares it."""
    out: dict[str, str] = {}
    for dep in deps:
        try:
            out[canonicalize_name(Requirement(dep).name)] = dep
        except InvalidRequirement:
            out[dep.strip()] = dep
    return out


def _pinned_version(requirement: str) -> str | None:
    """The version of a ``==`` pin, or None for any looser specifier."""
    try:
        specifiers = list(Requirement(requirement).specifier)
    except InvalidRequirement:
        return None
    if len(specifiers) == 1 and specifiers[0].operator == "==":
        return specifiers[0].version
    return None


def _resolve_dependency(
    name: str, base: str | None, ours: str | None, theirs: str | None
) -> Decision:
    """Apply three-way membership rules, falling back to pin comparison."""
    if ours is None and theirs is None:
        return Decision(name, None, "removed on both sides", False)
    if base is not None and ours is not None and theirs is None:
        return Decision(name, None, "upstream removed it", False)
    if base is not None and ours is None and theirs is not None:
        return Decision(name, None, "the fork removed it", False)
    if ours is None:
        return Decision(name, theirs, "upstream added it", False)
    if theirs is None:
        return Decision(name, ours, "the fork added it", False)

    if ours == theirs:
        return Decision(name, ours, "both sides agree", False)
    if ours == base:
        return Decision(name, theirs, "only upstream moved", False)
    if theirs == base:
        return Decision(name, ours, "only the fork moved", False)

    ours_version = _pinned_version(ours)
    theirs_version = _pinned_version(theirs)
    if ours_version is None or theirs_version is None:
        return Decision(
            name, ours, f"both sides changed it differently: {ours!r} vs {theirs!r}", True
        )

    pin = resolve_pin(_pinned_version(base) if base else None, ours_version, theirs_version)
    winner = ours if pin.value == ours_version else theirs
    return Decision(name, winner, pin.reason, pin.needs_review)


def _section_bounds(lines: list[str], section: str) -> tuple[int, int]:
    """The half-open line range owned by ``[section]``."""
    start = 0
    if section:
        header = f"[{section}]"
        for i, line in enumerate(lines):
            if line.strip() == header:
                start = i + 1
                break
        else:
            return (0, 0)
    for i in range(start, len(lines)):
        stripped = lines[i].lstrip()
        if stripped.startswith("[") and i != start - 1:
            return (start, i)
    return (start, len(lines))


def _value_span(lines: list[str], start: int) -> int:
    """Line index just past a value that may run across several lines."""
    depth = 0
    for i in range(start, len(lines)):
        depth += lines[i].count("[") + lines[i].count("{")
        depth -= lines[i].count("]") + lines[i].count("}")
        if i > start or depth <= 0:
            if depth <= 0:
                return i + 1
    return len(lines)


def _find_key(lines: list[str], section: str, key: str) -> tuple[int, int] | None:
    lo, hi = _section_bounds(lines, section)
    for i in range(lo, hi):
        stripped = lines[i].lstrip()
        if stripped.startswith(f"{key} ") or stripped.startswith(f"{key}="):
            after = stripped[len(key) :].lstrip()
            if after.startswith("="):
                # A value opening a bracket continues until it balances.
                head = after[1:]
                if head.count("[") > head.count("]") or head.count("{") > head.count("}"):
                    return (i, _value_span(lines, i))
                return (i, i + 1)
    return None


def _apply_identity(theirs_text: str, ours_text: str, identity_keys: list[str]) -> str:
    their_lines = theirs_text.splitlines(keepends=True)
    our_lines = ours_text.splitlines(keepends=True)

    # Replace from the bottom up so earlier spans keep their indices.
    replacements: list[tuple[int, int, list[str]]] = []
    for dotted in identity_keys:
        section, _, key = dotted.rpartition(".")
        ours_span = _find_key(our_lines, section, key)
        theirs_span = _find_key(their_lines, section, key)
        if ours_span is None or theirs_span is None:
            continue
        replacements.append(
            (theirs_span[0], theirs_span[1], our_lines[ours_span[0] : ours_span[1]])
        )

    for start, end, block in sorted(replacements, reverse=True):
        their_lines[start:end] = block
    return "".join(their_lines)


def _rewrite_dependencies(text: str, deps: list[str]) -> str:
    lines = text.splitlines(keepends=True)
    span = _find_key(lines, "project", "dependencies")
    if span is None:
        return text
    start, end = span
    indent = "    "
    block = ["dependencies = [\n"]
    block += [f'{indent}"{dep}",\n' for dep in deps]
    block.append("]\n")
    lines[start:end] = block
    return "".join(lines)


def merge_pyproject(
    base: str, ours: str, theirs: str, identity_keys: list[str]
) -> ManifestMerge:
    """Merge ``ours`` and ``theirs`` over ``base``, keeping upstream's document."""
    base_deps = _index(tomllib.loads(base).get("project", {}).get("dependencies", []))
    our_deps = _index(tomllib.loads(ours).get("project", {}).get("dependencies", []))
    their_deps = _index(tomllib.loads(theirs).get("project", {}).get("dependencies", []))

    # Upstream's order first, so the merged file reads like upstream's.
    ordered = list(their_deps) + [name for name in our_deps if name not in their_deps]

    decisions: list[Decision] = []
    resolved: list[str] = []
    for name in ordered:
        decision = _resolve_dependency(
            name, base_deps.get(name), our_deps.get(name), their_deps.get(name)
        )
        decisions.append(decision)
        if decision.value is not None:
            resolved.append(decision.value)

    text = _apply_identity(theirs, ours, identity_keys)
    text = _rewrite_dependencies(text, resolved)
    return ManifestMerge(text=text, decisions=decisions)


_RANGE = re.compile(r"^([\^~><=v\s]*)(\d[\w.+-]*)$")


def _split_range(spec: str) -> tuple[str, str] | None:
    """Split an npm range into its operator prefix and bare version."""
    match = _RANGE.match(spec.strip())
    if not match:
        return None
    return match.group(1), match.group(2)


def _resolve_npm(name: str, base: str | None, ours: str | None, theirs: str | None) -> Decision:
    if ours is None and theirs is None:
        return Decision(name, None, "removed on both sides", False)
    if base is not None and ours is not None and theirs is None:
        return Decision(name, None, "upstream removed it", False)
    if base is not None and ours is None and theirs is not None:
        return Decision(name, None, "the fork removed it", False)
    if ours is None:
        return Decision(name, theirs, "upstream added it", False)
    if theirs is None:
        return Decision(name, ours, "the fork added it", False)

    if ours == theirs:
        return Decision(name, ours, "both sides agree", False)
    if ours == base:
        return Decision(name, theirs, "only upstream moved", False)
    if theirs == base:
        return Decision(name, ours, "only the fork moved", False)

    ours_parts = _split_range(ours)
    theirs_parts = _split_range(theirs)
    if ours_parts is None or theirs_parts is None:
        return Decision(
            name, ours, f"unparseable range: {ours!r} vs {theirs!r}", True
        )

    base_parts = _split_range(base) if base else None
    pin = resolve_pin(
        base_parts[1] if base_parts else None, ours_parts[1], theirs_parts[1]
    )
    winner = ours if pin.value == ours_parts[1] else theirs
    return Decision(name, winner, pin.reason, pin.needs_review)


def merge_package_json(
    base: str, ours: str, theirs: str, identity_keys: list[str]
) -> ManifestMerge:
    """Merge a package.json, keeping upstream's document and the fork's identity."""
    base_doc, our_doc, their_doc = json.loads(base), json.loads(ours), json.loads(theirs)
    merged = dict(their_doc)

    for key in identity_keys:
        if key in our_doc:
            merged[key] = our_doc[key]

    decisions: list[Decision] = []
    for block in ("dependencies", "devDependencies", "optionalDependencies"):
        base_deps = base_doc.get(block, {})
        our_deps = our_doc.get(block, {})
        their_deps = their_doc.get(block, {})
        if not (base_deps or our_deps or their_deps):
            continue

        ordered = list(their_deps) + [n for n in our_deps if n not in their_deps]
        resolved: dict[str, str] = {}
        for name in ordered:
            decision = _resolve_npm(
                name, base_deps.get(name), our_deps.get(name), their_deps.get(name)
            )
            decisions.append(decision)
            if decision.value is not None:
                resolved[name] = decision.value
        merged[block] = resolved

    return ManifestMerge(text=json.dumps(merged, indent=2) + "\n", decisions=decisions)
