"""Loading and applying .github/upstream-sync-policy.yml."""

import pytest

from scripts.upstream_sync.policy import (
    PathClass,
    Policy,
    PolicyError,
)


def _policy(**classes):
    return Policy.from_dict(classes)


def test_a_path_in_no_class_is_left_for_git_to_merge():
    policy = _policy(fork_owned=["CHANGELOG.md"])

    assert policy.classify("boneio/webui/app.py") is PathClass.MERGE


def test_exact_path_is_matched():
    policy = _policy(fork_owned=["CHANGELOG.md"])

    assert policy.classify("CHANGELOG.md") is PathClass.FORK_OWNED


def test_recursive_glob_matches_nested_paths():
    policy = _policy(fork_owned=[".github/workflows/**"])

    assert policy.classify(".github/workflows/test.yml") is PathClass.FORK_OWNED


def test_recursive_glob_matches_deeply_nested_paths():
    policy = _policy(fork_owned=[".github/workflows/**"])

    assert policy.classify(".github/workflows/nested/deep.yml") is PathClass.FORK_OWNED


def test_recursive_glob_does_not_match_a_sibling_directory():
    policy = _policy(fork_owned=[".github/workflows/**"])

    assert policy.classify(".github/dependabot.yml") is PathClass.MERGE


def test_single_star_does_not_cross_a_directory_boundary():
    policy = _policy(fork_owned=["docs/*.md"])

    assert policy.classify("docs/GUIDE.md") is PathClass.FORK_OWNED
    assert policy.classify("docs/nested/GUIDE.md") is PathClass.MERGE


def test_regenerate_entries_carry_the_command_that_rebuilds_them():
    policy = Policy.from_dict(
        {"regenerate": [{"path": "uv.lock", "command": "uv lock"}]}
    )

    assert policy.classify("uv.lock") is PathClass.REGENERATE
    assert policy.regenerate_commands() == [("uv.lock", "uv lock")]


def test_manifest_entries_carry_their_identity_keys():
    policy = Policy.from_dict(
        {
            "manifests": [
                {"path": "pyproject.toml", "identity_keys": ["project.name"]}
            ]
        }
    )

    assert policy.classify("pyproject.toml") is PathClass.MANIFEST
    assert policy.identity_keys("pyproject.toml") == ["project.name"]


def test_a_path_claimed_by_two_classes_is_rejected_at_load_time():
    """Silent precedence between classes would be impossible to reason about."""
    with pytest.raises(PolicyError, match="uv.lock"):
        _policy(fork_owned=["uv.lock"], union=["uv.lock"])


def test_an_unknown_class_is_rejected_rather_than_ignored():
    with pytest.raises(PolicyError, match="frok_owned"):
        Policy.from_dict({"frok_owned": ["CHANGELOG.md"]})


def test_an_empty_class_is_allowed():
    policy = _policy(fork_deleted=[])

    assert policy.classify("anything") is PathClass.MERGE


def test_a_null_class_is_treated_as_empty():
    """`fork_deleted:` with nothing under it parses as None, not a list."""
    policy = _policy(fork_deleted=None)

    assert policy.classify("anything") is PathClass.MERGE


def test_the_repository_policy_file_loads_and_is_self_consistent():
    """The checked-in policy must never be ambiguous or malformed."""
    policy = Policy.load_default()

    assert policy.classify("uv.lock") is PathClass.REGENERATE
    assert policy.classify(".github/workflows/test.yml") is PathClass.FORK_OWNED
    assert policy.classify("frontend/package-lock.json") is PathClass.UPSTREAM_DELETED
    assert policy.classify("pyproject.toml") is PathClass.MANIFEST
    assert policy.classify(".gitignore") is PathClass.UNION
    assert policy.classify("boneio/webui/app.py") is PathClass.MERGE
