"""Apply an upstream batch to the fork, resolving everything policy can.

A conflict is never a failure here. Whatever survives is left in the tree with
its markers so the workflow can open a draft pull request against it.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .manifests import Decision, merge_package_json, merge_pyproject
from .patch_filter import filter_patch
from .policy import PathClass, Policy
from .report import build_report
from .union import union_merge

CONFLICT_MARKER = "<<<<<<<"

#: Semantic mergers by file extension. A manifest with no entry here is
#: reported rather than silently dropped.
_MERGERS = {".toml": merge_pyproject, ".json": merge_package_json}


def _write_text(path: Path, text: str) -> None:
    """Write text that may carry surrogate-escaped bytes, without translation."""
    path.write_bytes(text.encode("utf-8", errors="surrogateescape"))


@dataclass
class SyncResult:
    conflicts: list[str] = field(default_factory=list)
    unapplied: list[str] = field(default_factory=list)
    dropped: dict[str, PathClass] = field(default_factory=dict)
    manifest_decisions: dict[str, list[Decision]] = field(default_factory=dict)
    regenerated: list[str] = field(default_factory=list)
    report: str = ""

    @property
    def needs_human(self) -> bool:
        return bool(self.conflicts) or bool(self.unapplied) or any(
            decision.needs_review
            for decisions in self.manifest_decisions.values()
            for decision in decisions
        )


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run git, decoding output so that bytes which are not UTF-8 survive.

    Capture stays in binary mode: text mode would translate newlines, and a
    patch carrying a lone CR (the signature files do) must not be rewritten.
    """
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=check)
    return subprocess.CompletedProcess(
        result.args,
        result.returncode,
        result.stdout.decode("utf-8", errors="surrogateescape"),
        result.stderr.decode("utf-8", errors="surrogateescape"),
    )


def _show(repo: Path, ref: str, path: str) -> str | None:
    """File content at a ref, or None if it does not exist there."""
    result = _git(repo, "show", f"{ref}:{path}", check=False)
    return result.stdout if result.returncode == 0 else None


def _tracked_paths(repo: Path, base: str, end: str) -> list[str]:
    out = _git(repo, "diff", "--name-only", base, end).stdout
    return [line for line in out.splitlines() if line]


def run_sync(
    repo: Path,
    base: str,
    end: str,
    policy: Policy,
    skip_regeneration: bool = False,
) -> SyncResult:
    result = SyncResult()

    patch = _git(repo, "diff", "--binary", "--full-index", base, end).stdout
    filtered = filter_patch(patch, policy)
    result.dropped = filtered.dropped

    # Applied one file at a time: `git apply --index` is all-or-nothing, so a
    # single unappliable file would otherwise roll the whole batch back.
    patch_file = repo / ".git" / "upstream-sync.patch"
    for section in filtered.sections:
        patch_file.write_bytes(section.text.encode("utf-8", errors="surrogateescape"))
        applied = _git(repo, "apply", "--3way", "--index", str(patch_file), check=False)
        # A conflict is an expected outcome; only a hard failure is unapplied.
        if applied.returncode != 0 and "with conflicts" not in applied.stderr:
            result.unapplied.append(section.primary)
    patch_file.unlink(missing_ok=True)

    changed = _tracked_paths(repo, base, end)

    for path in changed:
        path_class = policy.classify(path)

        if path_class is PathClass.UPSTREAM_DELETED:
            _git(repo, "rm", "-q", "-f", "--ignore-unmatch", path, check=False)

        elif path_class is PathClass.UNION:
            ours = _show(repo, "HEAD", path) or ""
            theirs = _show(repo, end, path) or ""
            _write_text(repo / path, union_merge(ours, theirs))
            _git(repo, "add", path)

        elif path_class is PathClass.MANIFEST:
            merger = _MERGERS.get(Path(path).suffix)
            base_text = _show(repo, base, path)
            ours_text = _show(repo, "HEAD", path)
            theirs_text = _show(repo, end, path)
            if merger is None or None in (base_text, ours_text, theirs_text):
                # A manifest is dropped from the patch, so failing to merge it
                # would discard upstream's change without a trace.
                result.unapplied.append(path)
                continue
            merged = merger(
                base=base_text,
                ours=ours_text,
                theirs=theirs_text,
                identity_keys=policy.identity_keys(path),
            )
            _write_text(repo / path, merged.text)
            _git(repo, "add", path)
            result.manifest_decisions[path] = merged.decisions

    if not skip_regeneration:
        for path, command in policy.regenerate_commands():
            completed = subprocess.run(
                command, cwd=repo, shell=True, capture_output=True, text=True
            )
            if completed.returncode == 0:
                result.regenerated.append(path)
                _git(repo, "add", path, check=False)

    result.conflicts = _find_conflicts(repo, changed, policy)
    result.unapplied = sorted(set(result.unapplied) - set(result.conflicts))
    result.report = build_report(
        dropped=result.dropped,
        manifest_decisions=result.manifest_decisions,
        regenerated=result.regenerated,
        conflicts=result.conflicts,
        unapplied=result.unapplied,
    )
    return result


def _find_conflicts(repo: Path, changed: list[str], policy: Policy) -> list[str]:
    conflicts: list[str] = []
    for path in changed:
        if policy.classify(path) is not PathClass.MERGE:
            continue
        target = repo / path
        if not target.is_file():
            continue
        text = target.read_bytes().decode("utf-8", errors="surrogateescape")
        if CONFLICT_MARKER in text:
            conflicts.append(path)
    return sorted(conflicts)
