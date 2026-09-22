"""Semantic three-way merge of pyproject.toml.

Git merges a pinned-dependency array by hunk, so contiguous pin lines conflict
en bloc even where both sides made the identical bump. This merges per
dependency instead.
"""

import pytest

from scripts.upstream_sync.manifests import merge_pyproject

IDENTITY = [
    "project.name",
    "project.description",
    "project.urls.Repository",
]


def _toml(name, deps, repo="https://example.invalid/upstream", description="upstream"):
    lines = [
        "[project]",
        f'name = "{name}"',
        f'description = "{description}"',
        "dependencies = [",
    ]
    lines += [f'    "{dep}",' for dep in deps]
    lines += [
        "]",
        "",
        "[project.urls]",
        f'Repository = "{repo}"',
        "",
    ]
    return "\n".join(lines)


def _merge(base_deps, our_deps, their_deps, **kwargs):
    return merge_pyproject(
        base=_toml("boneio", base_deps),
        ours=_toml(
            "blackbone",
            our_deps,
            repo="https://github.com/smarthome-wroclaw/blackbone",
            description="fork",
        ),
        theirs=_toml("boneio", their_deps),
        identity_keys=IDENTITY,
        **kwargs,
    )


def _deps(result):
    import tomllib

    return tomllib.loads(result.text)["project"]["dependencies"]


def test_the_fork_keeps_its_identity_keys():
    result = _merge(["a==1.0"], ["a==1.0"], ["a==1.0"])

    import tomllib

    parsed = tomllib.loads(result.text)
    assert parsed["project"]["name"] == "blackbone"
    assert parsed["project"]["description"] == "fork"
    assert (
        parsed["project"]["urls"]["Repository"]
        == "https://github.com/smarthome-wroclaw/blackbone"
    )


def test_a_dependency_upstream_added_is_taken():
    result = _merge(["a==1.0"], ["a==1.0"], ["a==1.0", "starlette>=1.3.1"])

    assert "starlette>=1.3.1" in _deps(result)


def test_a_dependency_upstream_removed_is_dropped():
    """Upstream swapped python-jose for PyJWT; the fork should follow."""
    result = _merge(
        base_deps=["python-jose==3.5.0"],
        our_deps=["python-jose==3.5.0"],
        their_deps=["PyJWT==2.14.0"],
    )

    assert _deps(result) == ["PyJWT==2.14.0"]


def test_a_dependency_the_fork_added_is_kept():
    result = _merge(
        base_deps=["a==1.0"],
        our_deps=["a==1.0", "fork-only==9.9"],
        their_deps=["a==1.0"],
    )

    assert "fork-only==9.9" in _deps(result)


def test_a_dependency_the_fork_removed_stays_removed():
    result = _merge(
        base_deps=["a==1.0", "unwanted==2.0"],
        our_deps=["a==1.0"],
        their_deps=["a==1.0", "unwanted==2.0"],
    )

    assert "unwanted==2.0" not in _deps(result)


def test_identical_bumps_on_both_sides_merge_without_review():
    result = _merge(["aiohttp==3.14.1"], ["aiohttp==3.14.3"], ["aiohttp==3.14.3"])

    assert _deps(result) == ["aiohttp==3.14.3"]
    assert result.needs_review is False


def test_the_higher_pin_wins_when_both_sides_moved_up():
    result = _merge(
        ["python-multipart==0.0.22"],
        ["python-multipart==0.0.32"],
        ["python-multipart==0.0.31"],
    )

    assert _deps(result) == ["python-multipart==0.0.32"]


def test_an_upstream_downgrade_flags_the_merge_for_review():
    result = _merge(["requests==2.33.0"], ["requests==2.34.2"], ["requests==2.32.5"])

    assert result.needs_review is True
    assert any("requests" in d.name for d in result.decisions if d.needs_review)


def test_extras_are_preserved_on_the_resolved_requirement():
    result = _merge(
        ["w1thermsensor[async]==2.2.0"],
        ["w1thermsensor[async]==2.3.0"],
        ["w1thermsensor[async]==2.2.0"],
    )

    assert _deps(result) == ["w1thermsensor[async]==2.3.0"]


def test_an_environment_marker_is_preserved():
    marked = "cryptography>=50.0.0; platform_system == 'Linux'"
    result = _merge(["a==1.0"], ["a==1.0"], ["a==1.0", marked])

    assert any("platform_system" in dep for dep in _deps(result))


def test_a_non_equality_specifier_is_carried_through():
    result = _merge(["aioesphomeapi>=29.0.0"], ["aioesphomeapi>=29.0.0"], ["aioesphomeapi>=45.0.0"])

    assert _deps(result) == ["aioesphomeapi>=45.0.0"]


def test_every_dependency_produces_a_decision_for_the_pr_body():
    result = _merge(["a==1.0"], ["a==1.2"], ["a==1.1"])

    names = {d.name for d in result.decisions}
    assert "a" in names
    assert all(d.reason for d in result.decisions)


def test_upstream_comments_outside_the_dependency_array_survive():
    theirs = '[project]\nname = "boneio"\n# upstream note\ndescription = "upstream"\ndependencies = [\n    "a==1.0",\n]\n\n[project.urls]\nRepository = "https://example.invalid/upstream"\n'
    result = merge_pyproject(
        base=_toml("boneio", ["a==1.0"]),
        ours=_toml("blackbone", ["a==1.0"], description="fork"),
        theirs=theirs,
        identity_keys=IDENTITY,
    )

    assert "# upstream note" in result.text


def test_the_merged_document_is_valid_toml():
    import tomllib

    result = _merge(["a==1.0"], ["a==1.2", "b==2.0"], ["a==1.1", "c==3.0"])

    tomllib.loads(result.text)
