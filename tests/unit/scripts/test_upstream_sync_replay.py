"""Replay the real upstream backlog through the pipeline.

This pins the checked-in policy against real data. It asserts invariants
rather than an exact file list, because both `origin/main` and the upstream
branch move; a hardcoded set would be flaky by construction.

Skips when the upstream ref has not been fetched, which is the normal case
outside the sync workflow.
"""

import subprocess
import tomllib
from pathlib import Path

import pytest

from scripts.upstream_sync.apply import run_sync
from scripts.upstream_sync.policy import PathClass, Policy

REPO_ROOT = Path(__file__).resolve().parents[3]
UPSTREAM_REF = "refs/remotes/source/dev-debian13"
FORK_REF = "refs/remotes/origin/main"

#: Paths whose conflicts the policy exists to eliminate. None may ever reach
#: a human again.
MECHANICAL = [
    "uv.lock",
    "frontend/pnpm-lock.yaml",
    "frontend/package-lock.json",
    "pyproject.toml",
    "frontend/package.json",
    ".github/workflows/test.yml",
    ".gitignore",
    "CHANGELOG.md",
    "boneio/version.py",
]


def _rev(ref: str) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or None


def _clone(tmp: Path, fork: str) -> Path:
    clone = tmp / "repo"
    subprocess.run(
        ["git", "clone", "-q", "--shared", "--no-checkout", str(REPO_ROOT), str(clone)],
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "checkout", "-q", "--detach", fork], cwd=clone, check=True)
    return clone


@pytest.fixture(scope="module")
def refs():
    upstream, fork = _rev(UPSTREAM_REF), _rev(FORK_REF)
    if not upstream or not fork:
        pytest.skip(f"{UPSTREAM_REF} not fetched; nothing to replay")
    return fork, upstream


@pytest.fixture(scope="module")
def replay(tmp_path_factory, refs):
    fork, upstream = refs
    clone = _clone(tmp_path_factory.mktemp("replay"), fork)
    base = subprocess.run(
        ["git", "merge-base", fork, upstream],
        cwd=clone,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    result = run_sync(
        repo=clone,
        base=base,
        end=upstream,
        policy=Policy.load_default(),
        skip_regeneration=True,
    )
    return result, clone


@pytest.fixture(scope="module")
def unfiltered(tmp_path_factory, refs):
    """The same batch with an empty policy, as a baseline to measure against."""
    fork, upstream = refs
    clone = _clone(tmp_path_factory.mktemp("baseline"), fork)
    base = subprocess.run(
        ["git", "merge-base", fork, upstream],
        cwd=clone,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return run_sync(
        repo=clone,
        base=base,
        end=upstream,
        policy=Policy.from_dict({}),
        skip_regeneration=True,
    )


@pytest.mark.slow
def test_the_batch_actually_applies_rather_than_rolling_back(replay):
    """A single unappliable file used to roll the whole batch back."""
    result, clone = replay
    changed = subprocess.run(
        ["git", "status", "--porcelain"], cwd=clone, capture_output=True, text=True
    ).stdout.splitlines()

    assert len(changed) > 100


@pytest.mark.slow
def test_no_mechanical_file_ever_reaches_a_human(replay):
    result, _ = replay
    reached = set(result.conflicts) | set(result.unapplied)

    assert reached.isdisjoint(MECHANICAL)


@pytest.mark.slow
def test_every_remaining_conflict_is_genuine_code_overlap(replay):
    """Nothing the policy claims should ever appear as a conflict."""
    result, _ = replay
    policy = Policy.load_default()

    assert all(policy.classify(path) is PathClass.MERGE for path in result.conflicts)


@pytest.mark.slow
def test_the_policy_measurably_reduces_what_a_human_must_resolve(replay, unfiltered):
    result, _ = replay
    before = set(unfiltered.conflicts) | set(unfiltered.unapplied)
    after = set(result.conflicts) | set(result.unapplied)

    assert after < before


@pytest.mark.slow
def test_the_merged_pyproject_is_valid_and_keeps_the_fork_identity(replay):
    _, clone = replay
    parsed = tomllib.loads((clone / "pyproject.toml").read_text())

    assert parsed["project"]["name"] == "blackbone"
    assert "smarthome-wroclaw" in parsed["project"]["urls"]["Repository"]


@pytest.mark.slow
def test_upstreams_security_migration_survives_the_merge(replay):
    """Upstream swapped python-jose for PyJWT; a blunt ours-wins would lose it."""
    result, clone = replay
    deps = tomllib.loads((clone / "pyproject.toml").read_text())["project"]["dependencies"]

    assert any(dep.startswith("PyJWT") for dep in deps)
    assert not any(dep.startswith("python-jose") for dep in deps)


@pytest.mark.slow
def test_the_fork_keeps_its_own_pin_where_it_is_ahead_of_upstream(replay):
    _, clone = replay
    deps = tomllib.loads((clone / "pyproject.toml").read_text())["project"]["dependencies"]
    pins = {dep.split("==")[0]: dep for dep in deps if "==" in dep}

    assert pins["requests"] == "requests==2.34.2"


@pytest.mark.slow
def test_a_real_batch_with_conflicts_is_reported_as_needing_a_human(replay):
    result, _ = replay

    assert result.needs_human is (bool(result.conflicts) or bool(result.unapplied))
