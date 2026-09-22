"""Entry point the sync workflow calls to apply an upstream batch."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .apply import run_sync
from .policy import Policy, PolicyError


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="upstream-sync")
    parser.add_argument("--repo", default=".", type=Path)
    parser.add_argument("--base", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--policy", type=Path, default=None)
    parser.add_argument("--report-file", type=Path, required=True)
    parser.add_argument("--github-output", type=Path, default=None)
    parser.add_argument("--skip-regeneration", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)

    try:
        policy = Policy.load(args.policy) if args.policy else Policy.load_default()
    except (PolicyError, OSError) as exc:
        print(f"upstream-sync: unusable policy: {exc}", file=sys.stderr)
        return 2

    try:
        result = run_sync(
            repo=args.repo,
            base=args.base,
            end=args.end,
            policy=policy,
            skip_regeneration=args.skip_regeneration,
        )
    except PolicyError as exc:
        print(f"upstream-sync: {exc}", file=sys.stderr)
        return 2

    args.report_file.write_text(result.report)

    if args.github_output:
        with args.github_output.open("a") as handle:
            handle.write(f"needs_human={str(result.needs_human).lower()}\n")
            handle.write(f"conflict_count={len(result.conflicts)}\n")
            handle.write(f"unapplied_count={len(result.unapplied)}\n")

    for path in result.conflicts:
        print(f"conflict: {path}")
    for path in result.unapplied:
        print(f"unapplied: {path}")
    print(
        f"upstream-sync: {len(result.conflicts)} conflict(s), "
        f"{len(result.unapplied)} unapplied, {len(result.dropped)} handled by policy"
    )

    # A conflict is a reviewable outcome, not a failure: the workflow opens a
    # draft pull request against it.
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
