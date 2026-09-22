"""Three-way resolution of a single pinned dependency.

The fork and upstream both run dependency updates, so the same pin moves on
both sides independently. These rules decide which side wins without a human.
"""

import pytest

from scripts.upstream_sync.versions import resolve_pin


def test_identical_bumps_on_both_sides_resolve_without_review():
    decision = resolve_pin(base="3.14.1", ours="3.14.3", theirs="3.14.3")

    assert decision.value == "3.14.3"
    assert decision.needs_review is False


def test_only_fork_moved_the_pin_keeps_the_fork_version():
    decision = resolve_pin(base="2.32.5", ours="2.34.2", theirs="2.32.5")

    assert decision.value == "2.34.2"
    assert decision.needs_review is False


def test_only_upstream_moved_the_pin_keeps_the_upstream_version():
    decision = resolve_pin(base="0.118.0", ours="0.118.0", theirs="0.141.1")

    assert decision.value == "0.141.1"
    assert decision.needs_review is False


def test_both_sides_moved_up_takes_the_higher_version():
    decision = resolve_pin(base="0.0.22", ours="0.0.32", theirs="0.0.31")

    assert decision.value == "0.0.32"
    assert decision.needs_review is False


def test_upstream_downgrade_is_flagged_for_review_and_never_auto_resolved():
    """A downgrade is usually a deliberate pin-back after a regression.

    Taking the higher version would silently undo it, so a human decides.
    """
    decision = resolve_pin(base="2.33.0", ours="2.34.2", theirs="2.32.5")

    assert decision.needs_review is True
    assert "downgrade" in decision.reason


def test_upstream_downgrade_is_flagged_even_when_the_fork_stood_still():
    decision = resolve_pin(base="2.33.0", ours="2.33.0", theirs="2.32.5")

    assert decision.needs_review is True


def test_pep440_ordering_is_used_rather_than_string_ordering():
    """String comparison would call "3.9.0" greater than "3.14.0"."""
    decision = resolve_pin(base="3.8.0", ours="3.14.0", theirs="3.9.0")

    assert decision.value == "3.14.0"


def test_prerelease_is_ordered_below_its_release():
    decision = resolve_pin(base="1.5.0", ours="1.6.0", theirs="1.6.0.dev11")

    assert decision.value == "1.6.0"


def test_a_pin_absent_from_base_still_resolves_to_the_higher_side():
    """The dependency was added on both sides at different versions."""
    decision = resolve_pin(base=None, ours="1.2.0", theirs="1.3.0")

    assert decision.value == "1.3.0"
    assert decision.needs_review is False


def test_unparseable_version_is_flagged_rather_than_guessed():
    decision = resolve_pin(base="1.0.0", ours="not-a-version", theirs="1.1.0")

    assert decision.needs_review is True
