"""End-to-end application of an upstream batch against a real git repository."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts.upstream_sync.apply import run_sync
from scripts.upstream_sync.policy import Policy

POLICY = {
    "fork_owned": ["CHANGELOG.md"],
    "upstream_deleted": ["vestigial.lock"],
    "union": [".gitignore"],
    "manifests": [{"path": "pyproject.toml", "identity_keys": ["project.name"]}],
}


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return result.stdout


def _write(repo: Path, name: str, text: str) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _pyproject(name: str, deps: list[str]) -> str:
    body = "\n".join(f'    "{d}",' for d in deps)
    return f'[project]\nname = "{name}"\ndependencies = [\n{body}\n]\n'


@dataclass
class Fork:
    """A fork checkout plus the upstream range waiting to be synced."""

    path: Path
    base: str
    end: str


@pytest.fixture
def repo(tmp_path: Path) -> Fork:
    """A fork that shares history with an upstream branch, then diverges."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")

    _write(repo, "CHANGELOG.md", "# base\n")
    _write(repo, "shared.py", "base line\n")
    _write(repo, "untouched.py", "base\n")
    _write(repo, "vestigial.lock", "base lock\n")
    _write(repo, ".gitignore", "base-ignore\n")
    _write(repo, "pyproject.toml", _pyproject("upstreamname", ["a==1.0", "gone==1.0"]))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD").strip()

    # Upstream continues on its own branch.
    _git(repo, "checkout", "-q", "-b", "upstream")
    _write(repo, "CHANGELOG.md", "# upstream rewrote this\n")
    _write(repo, "shared.py", "upstream line\n")
    _write(repo, "untouched.py", "upstream improved this\n")
    (repo / "vestigial.lock").unlink()
    _write(repo, ".gitignore", "base-ignore\nupstream-ignore\n")
    _write(repo, "pyproject.toml", _pyproject("upstreamname", ["a==1.1", "added==2.0"]))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "upstream work")
    end = _git(repo, "rev-parse", "HEAD").strip()

    # The fork diverges.
    _git(repo, "checkout", "-q", "main")
    _write(repo, "CHANGELOG.md", "# the fork owns this\n")
    _write(repo, "shared.py", "fork line\n")
    _write(repo, ".gitignore", "base-ignore\nfork-ignore\n")
    _write(repo, "pyproject.toml", _pyproject("forkname", ["a==1.0", "gone==1.0"]))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "fork work")

    return Fork(path=repo, base=base, end=end)


def _run(fork: Fork):
    return run_sync(
        repo=fork.path,
        base=fork.base,
        end=fork.end,
        policy=Policy.from_dict(POLICY),
        skip_regeneration=True,
    )


def test_an_unclaimed_file_takes_the_upstream_change(repo: Fork):
    _run(repo)

    assert (repo.path / "untouched.py").read_text() == "upstream improved this\n"


def test_a_fork_owned_file_keeps_the_fork_content(repo: Fork):
    _run(repo)

    assert (repo.path / "CHANGELOG.md").read_text() == "# the fork owns this\n"


def test_a_fork_owned_drop_is_reported(repo: Fork):
    result = _run(repo)

    assert "CHANGELOG.md" in result.dropped


def test_a_file_upstream_deleted_is_removed_from_the_fork(repo: Fork):
    _run(repo)

    assert not (repo.path / "vestigial.lock").exists()


def test_a_union_file_keeps_both_sides(repo: Fork):
    _run(repo)

    text = (repo.path / ".gitignore").read_text()
    assert "fork-ignore" in text
    assert "upstream-ignore" in text


def test_a_manifest_is_merged_semantically(repo: Fork):
    _run(repo)

    text = (repo.path / "pyproject.toml").read_text()
    assert 'name = "forkname"' in text     # fork identity survives
    assert "added==2.0" in text            # upstream's new dependency arrives
    assert "gone==1.0" not in text         # upstream's removal is followed
    assert "a==1.1" in text                # upstream's bump is taken


def test_a_genuine_overlap_is_reported_as_a_conflict(repo: Fork):
    result = _run(repo)

    assert "shared.py" in result.conflicts


def test_a_conflicted_file_keeps_its_markers_for_a_human(repo: Fork):
    _run(repo)

    assert "<<<<<<<" in (repo.path / "shared.py").read_text()


def test_policy_handled_files_are_not_reported_as_conflicts(repo: Fork):
    result = _run(repo)

    assert result.conflicts == ["shared.py"]


def test_the_report_names_the_conflict(repo: Fork):
    result = _run(repo)

    assert "shared.py" in result.report


def test_non_utf8_bytes_in_the_batch_do_not_break_the_patch(tmp_path: Path):
    """Signature files carry no NUL byte, so git emits their raw bytes as text.

    boneio/migrations/plans/*.sig are exactly this: not base85-encoded like a
    true binary, and not decodable as UTF-8 either.
    """
    repo = tmp_path / "binrepo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")

    (repo / "plan.sig").write_bytes(bytes([0x0D, 0xEA, 0xBE, 0xEF, 0xFF, 0xFE, 0x0A]))
    _write(repo, "keep.py", "base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD").strip()

    _git(repo, "checkout", "-q", "-b", "upstream")
    (repo / "plan.sig").write_bytes(bytes([0x0D, 0xEB, 0xBE, 0xEF, 0xFF, 0xFE, 0x0A]))
    _write(repo, "keep.py", "upstream\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "upstream signature change")
    end = _git(repo, "rev-parse", "HEAD").strip()

    _git(repo, "checkout", "-q", "main")

    result = run_sync(
        repo=repo,
        base=base,
        end=end,
        policy=Policy.from_dict({}),
        skip_regeneration=True,
    )

    assert result.conflicts == []
    assert (repo / "keep.py").read_text() == "upstream\n"
    assert (repo / "plan.sig").read_bytes()[1] == 0xEB


@pytest.fixture
def fork_with_unappliable_file(tmp_path: Path) -> Fork:
    """The fork deleted a file that upstream then modified.

    Its hunk can never apply. Applying the batch as one patch would roll the
    whole thing back, losing every other file's changes too.
    """
    repo = tmp_path / "hardfail"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")

    _write(repo, "removed_by_fork.py", "base\n")
    _write(repo, "other.py", "base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD").strip()

    _git(repo, "checkout", "-q", "-b", "upstream")
    _write(repo, "removed_by_fork.py", "upstream changed this\n")
    _write(repo, "other.py", "upstream improved this\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "upstream work")
    end = _git(repo, "rev-parse", "HEAD").strip()

    _git(repo, "checkout", "-q", "main")
    _git(repo, "rm", "-q", "removed_by_fork.py")
    _git(repo, "commit", "-qm", "fork removed it")

    return Fork(path=repo, base=base, end=end)


def _run_plain(fork: Fork):
    return run_sync(
        repo=fork.path,
        base=fork.base,
        end=fork.end,
        policy=Policy.from_dict({}),
        skip_regeneration=True,
    )


def test_one_unappliable_file_does_not_roll_back_the_whole_batch(
    fork_with_unappliable_file: Fork,
):
    fork = fork_with_unappliable_file

    _run_plain(fork)

    assert (fork.path / "other.py").read_text() == "upstream improved this\n"


def test_an_unappliable_file_is_reported_rather_than_lost_silently(
    fork_with_unappliable_file: Fork,
):
    result = _run_plain(fork_with_unappliable_file)

    assert "removed_by_fork.py" in result.unapplied


def test_an_unappliable_file_makes_the_batch_need_a_human(
    fork_with_unappliable_file: Fork,
):
    result = _run_plain(fork_with_unappliable_file)

    assert result.needs_human is True


def test_the_report_names_the_unappliable_file(fork_with_unappliable_file: Fork):
    result = _run_plain(fork_with_unappliable_file)

    assert "removed_by_fork.py" in result.report


def test_a_manifest_type_with_no_merger_is_reported_not_silently_dropped(
    tmp_path: Path,
):
    """A manifest is dropped from the patch, so an unhandled one loses changes.

    Reporting it keeps that failure visible instead of quietly discarding
    upstream's work.
    """
    repo = tmp_path / "m"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "T")
    _write(repo, "deps.xml", "<deps>base</deps>\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "checkout", "-q", "-b", "upstream")
    _write(repo, "deps.xml", "<deps>upstream</deps>\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "up")
    end = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "checkout", "-q", "main")

    result = run_sync(
        repo=repo,
        base=base,
        end=end,
        policy=Policy.from_dict(
            {"manifests": [{"path": "deps.xml", "identity_keys": []}]}
        ),
        skip_regeneration=True,
    )

    assert "deps.xml" in result.unapplied


def test_a_package_json_manifest_is_merged(tmp_path: Path):
    import json

    repo = tmp_path / "j"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "T")

    def pkg(name, deps):
        return json.dumps({"name": name, "dependencies": deps}, indent=2) + "\n"

    _write(repo, "package.json", pkg("up", {"react": "19.0.0"}))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "checkout", "-q", "-b", "upstream")
    _write(repo, "package.json", pkg("up", {"react": "19.1.0", "zod": "4.0.0"}))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "up")
    end = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "checkout", "-q", "main")
    _write(repo, "package.json", pkg("fork", {"react": "19.2.0"}))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "fork")

    result = run_sync(
        repo=repo,
        base=base,
        end=end,
        policy=Policy.from_dict(
            {"manifests": [{"path": "package.json", "identity_keys": ["name"]}]}
        ),
        skip_regeneration=True,
    )

    merged = json.loads((repo / "package.json").read_text())
    assert merged["name"] == "fork"            # fork identity survives
    assert merged["dependencies"]["zod"] == "4.0.0"    # upstream's addition
    assert merged["dependencies"]["react"] == "19.2.0"  # fork is ahead
    assert "package.json" not in result.unapplied
