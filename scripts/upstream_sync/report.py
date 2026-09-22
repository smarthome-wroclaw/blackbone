"""Render what the sync decided automatically, for the pull request body."""

from __future__ import annotations

from .manifests import Decision
from .policy import PathClass

_QUIET = "both sides agree"


def build_report(
    dropped: dict[str, PathClass] | None = None,
    manifest_decisions: dict[str, list[Decision]] | None = None,
    regenerated: list[str] | None = None,
    conflicts: list[str] | None = None,
    unapplied: list[str] | None = None,
) -> str:
    dropped = dropped or {}
    manifest_decisions = manifest_decisions or {}
    regenerated = regenerated or []
    conflicts = conflicts or []
    unapplied = unapplied or []

    out: list[str] = []

    if conflicts:
        out += [
            "### Conflicts needing a human",
            "",
            "These files are committed with conflict markers. Resolve them on "
            "this branch, push, and mark the pull request ready.",
            "",
        ]
        out += [f"- `{path}`" for path in conflicts]
        out.append("")

    if unapplied:
        out += [
            "### Upstream changes that could not be applied",
            "",
            "These hunks did not apply at all, so upstream's change to them is "
            "**not** in this branch. Port them across by hand.",
            "",
        ]
        out += [f"- `{path}`" for path in unapplied]
        out.append("")

    review = [
        (path, decision)
        for path, decisions in manifest_decisions.items()
        for decision in decisions
        if decision.needs_review
    ]
    if review:
        out += ["### Needs review", ""]
        out += [
            f"- `{path}`: **{decision.name}** — {decision.reason}"
            for path, decision in review
        ]
        out.append("")

    for path, decisions in manifest_decisions.items():
        changed = [d for d in decisions if d.reason != _QUIET and not d.needs_review]
        quiet = len(decisions) - len(changed) - len(
            [d for d in decisions if d.needs_review]
        )
        out += [f"### `{path}` resolved semantically", ""]
        if changed:
            out += ["| Dependency | Result | Why |", "| --- | --- | --- |"]
            for decision in changed:
                value = f"`{decision.value}`" if decision.value else "_removed_"
                out.append(f"| `{decision.name}` | {value} | {decision.reason} |")
            out.append("")
        out.append(f"{quiet} further dependencies were identical on both sides.")
        out.append("")

    if regenerated:
        out += ["### Regenerated rather than merged", ""]
        out += [f"- `{path}`" for path in regenerated]
        out.append("")

    if dropped:
        out += [
            "### Upstream changes dropped by policy",
            "",
            "Listed so upstream's evolution of these paths stays visible.",
            "",
            "| Path | Class |",
            "| --- | --- |",
        ]
        out += [
            f"| `{path}` | `{path_class.value}` |"
            for path, path_class in sorted(dropped.items())
        ]
        out.append("")

    if not out:
        return "No manual steps: the whole batch applied without conflict.\n"

    return "\n".join(out).rstrip() + "\n"
