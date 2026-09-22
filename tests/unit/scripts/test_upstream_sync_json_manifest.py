"""Semantic three-way merge of package.json."""

import json

from scripts.upstream_sync.manifests import merge_package_json

IDENTITY = ["name", "description"]


def _pkg(name, deps, dev=None, description="upstream"):
    doc = {"name": name, "description": description, "dependencies": deps}
    if dev is not None:
        doc["devDependencies"] = dev
    return json.dumps(doc, indent=2) + "\n"


def _merge(base, ours, theirs, **kw):
    return merge_package_json(
        base=_pkg("frontend", base),
        ours=_pkg("frontend", ours, description="fork", **kw),
        theirs=_pkg("frontend", theirs),
        identity_keys=IDENTITY,
    )


def _deps(result):
    return json.loads(result.text)["dependencies"]


def test_the_fork_keeps_its_identity_keys():
    result = _merge({"react": "19.0.0"}, {"react": "19.0.0"}, {"react": "19.0.0"})

    assert json.loads(result.text)["description"] == "fork"


def test_a_dependency_upstream_added_is_taken():
    result = _merge({"react": "19.0.0"}, {"react": "19.0.0"}, {"react": "19.0.0", "zod": "4.0.0"})

    assert _deps(result)["zod"] == "4.0.0"


def test_a_dependency_upstream_removed_is_dropped():
    result = _merge({"old": "1.0.0"}, {"old": "1.0.0"}, {})

    assert "old" not in _deps(result)


def test_a_dependency_the_fork_added_is_kept():
    result = _merge({}, {"forkonly": "1.0.0"}, {})

    assert _deps(result)["forkonly"] == "1.0.0"


def test_the_higher_version_wins_when_both_sides_moved_up():
    result = _merge({"react": "19.0.0"}, {"react": "19.2.0"}, {"react": "19.1.0"})

    assert _deps(result)["react"] == "19.2.0"


def test_a_caret_range_is_compared_on_its_version():
    result = _merge({"react": "^19.0.0"}, {"react": "^19.2.0"}, {"react": "^19.1.0"})

    assert _deps(result)["react"] == "^19.2.0"


def test_an_upstream_downgrade_is_flagged_for_review():
    result = _merge({"react": "19.1.0"}, {"react": "19.2.0"}, {"react": "19.0.0"})

    assert result.needs_review is True


def test_dev_dependencies_are_merged_too():
    result = merge_package_json(
        base=_pkg("frontend", {}, dev={"vite": "8.0.0"}),
        ours=_pkg("frontend", {}, dev={"vite": "8.2.0"}),
        theirs=_pkg("frontend", {}, dev={"vite": "8.3.0"}),
        identity_keys=IDENTITY,
    )

    assert json.loads(result.text)["devDependencies"]["vite"] == "8.3.0"


def test_an_unparseable_range_is_flagged_rather_than_guessed():
    result = _merge({"pkg": "1.0.0"}, {"pkg": "workspace:*"}, {"pkg": "2.0.0"})

    assert result.needs_review is True


def test_the_merged_document_is_valid_json():
    result = _merge({"a": "1.0.0"}, {"a": "1.2.0"}, {"a": "1.1.0", "b": "2.0.0"})

    json.loads(result.text)
