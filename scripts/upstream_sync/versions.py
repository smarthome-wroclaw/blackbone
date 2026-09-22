"""Three-way resolution of a single pinned dependency version."""

from __future__ import annotations

from dataclasses import dataclass

from packaging.version import InvalidVersion, Version


@dataclass(frozen=True)
class PinDecision:
    """How one dependency pin was resolved, and whether a human must look."""

    value: str
    reason: str
    needs_review: bool


def resolve_pin(base: str | None, ours: str, theirs: str) -> PinDecision:
    """Resolve a pin that the fork (``ours``) and upstream (``theirs``) both hold.

    ``base`` is the version at the point the two sides last agreed, or None if
    the dependency did not exist there.
    """
    if ours == theirs:
        return PinDecision(ours, "both sides agree", False)

    try:
        ours_v = Version(ours)
        theirs_v = Version(theirs)
        base_v = Version(base) if base is not None else None
    except InvalidVersion as exc:
        return PinDecision(ours, f"unparseable version: {exc}", True)

    if base_v is not None and theirs_v < base_v:
        return PinDecision(
            ours,
            f"upstream downgrade {base} -> {theirs}, needs a human",
            True,
        )

    if base_v is not None and ours_v == base_v:
        return PinDecision(theirs, "only upstream moved", False)

    if base_v is not None and theirs_v == base_v:
        return PinDecision(ours, "only the fork moved", False)

    if ours_v > theirs_v:
        return PinDecision(ours, "both moved up, fork is ahead", False)
    return PinDecision(theirs, "both moved up, upstream is ahead", False)
