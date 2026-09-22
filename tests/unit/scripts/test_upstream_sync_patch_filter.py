"""Dropping policy-owned paths out of an upstream patch before it is applied."""

import pytest

from scripts.upstream_sync.patch_filter import filter_patch
from scripts.upstream_sync.policy import PathClass, Policy

TWO_FILES = """\
diff --git a/CHANGELOG.md b/CHANGELOG.md
index 1111111..2222222 100644
--- a/CHANGELOG.md
+++ b/CHANGELOG.md
@@ -1,2 +1,2 @@
-old upstream heading
+new upstream heading
 unchanged
diff --git a/boneio/runner.py b/boneio/runner.py
index 3333333..4444444 100644
--- a/boneio/runner.py
+++ b/boneio/runner.py
@@ -1,2 +1,2 @@
-old code
+new code
 unchanged
"""


def _policy():
    return Policy.from_dict({"fork_owned": ["CHANGELOG.md"]})


def test_a_fork_owned_file_is_dropped_from_the_patch():
    result = filter_patch(TWO_FILES, _policy())

    assert "CHANGELOG.md" not in result.patch


def test_an_unclaimed_file_survives_the_filter():
    result = filter_patch(TWO_FILES, _policy())

    assert "boneio/runner.py" in result.patch
    assert "+new code" in result.patch


def test_the_surviving_patch_keeps_its_section_intact():
    result = filter_patch(TWO_FILES, _policy())

    assert result.patch == """\
diff --git a/boneio/runner.py b/boneio/runner.py
index 3333333..4444444 100644
--- a/boneio/runner.py
+++ b/boneio/runner.py
@@ -1,2 +1,2 @@
-old code
+new code
 unchanged
"""


def test_dropped_paths_are_reported_with_the_class_that_claimed_them():
    result = filter_patch(TWO_FILES, _policy())

    assert result.dropped == {"CHANGELOG.md": PathClass.FORK_OWNED}


def test_dropping_every_section_yields_an_empty_patch():
    policy = Policy.from_dict(
        {"fork_owned": ["CHANGELOG.md", "boneio/runner.py"]}
    )

    result = filter_patch(TWO_FILES, policy)

    assert result.patch == ""


def test_a_binary_section_is_carried_through_unchanged():
    patch = """\
diff --git a/boneio/assets/logo.png b/boneio/assets/logo.png
index 5555555..6666666 100644
GIT binary patch
literal 12
TcmZQzU|?_e0R#&90ssI21poj5

"""
    result = filter_patch(patch, Policy.from_dict({}))

    assert "GIT binary patch" in result.patch
    assert result.patch == patch


def test_a_regenerated_lockfile_is_dropped_so_it_can_be_rebuilt():
    patch = """\
diff --git a/uv.lock b/uv.lock
index 7777777..8888888 100644
--- a/uv.lock
+++ b/uv.lock
@@ -1,1 +1,1 @@
-version = 1
+version = 2
"""
    policy = Policy.from_dict(
        {"regenerate": [{"path": "uv.lock", "command": "uv lock"}]}
    )

    result = filter_patch(patch, policy)

    assert result.patch == ""
    assert result.dropped == {"uv.lock": PathClass.REGENERATE}


def test_a_rename_is_dropped_when_either_side_of_it_is_claimed():
    patch = """\
diff --git a/README.md b/docs/README.md
similarity index 100%
rename from README.md
rename to docs/README.md
"""
    policy = Policy.from_dict({"fork_owned": ["README.md"]})

    result = filter_patch(patch, policy)

    assert result.patch == ""


def test_a_path_containing_spaces_is_matched_correctly():
    patch = """\
diff --git a/docs/my notes.md b/docs/my notes.md
index 9999999..aaaaaaa 100644
--- a/docs/my notes.md
+++ b/docs/my notes.md
@@ -1,1 +1,1 @@
-a
+b
"""
    policy = Policy.from_dict({"fork_owned": ["docs/my notes.md"]})

    result = filter_patch(patch, policy)

    assert result.patch == ""


def test_an_empty_patch_filters_to_an_empty_patch():
    result = filter_patch("", Policy.from_dict({}))

    assert result.patch == ""
    assert result.dropped == {}
