"""Union merge, for files where both sides' lines should simply coexist."""

from scripts.upstream_sync.union import union_merge


def test_lines_unique_to_each_side_are_all_kept():
    result = union_merge(ours="a\nb\n", theirs="a\nc\n")

    assert result == "a\nb\nc\n"


def test_a_line_present_on_both_sides_appears_once():
    result = union_merge(ours="a\nb\n", theirs="b\na\n")

    assert result.count("a\n") == 1
    assert result.count("b\n") == 1


def test_the_fork_ordering_leads():
    result = union_merge(ours="z\ny\n", theirs="x\n")

    assert result == "z\ny\nx\n"


def test_blank_lines_and_comments_are_not_deduplicated_away():
    """Two sections may each legitimately end with a blank line."""
    result = union_merge(ours="# ours\n\na\n", theirs="# theirs\n\nb\n")

    assert result == "# ours\n\na\n# theirs\n\nb\n"


def test_an_empty_side_returns_the_other():
    assert union_merge(ours="", theirs="a\n") == "a\n"
    assert union_merge(ours="a\n", theirs="") == "a\n"


def test_a_file_without_a_trailing_newline_still_merges():
    result = union_merge(ours="a", theirs="b")

    assert result == "a\nb\n"
