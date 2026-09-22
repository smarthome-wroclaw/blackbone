"""The command line the workflow calls."""

import subprocess
from pathlib import Path

import pytest

from scripts.upstream_sync.cli import main

REPO_ROOT = Path(__file__).resolve().parents[3]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def clean_fork(tmp_path: Path):
    """A fork whose upstream batch applies without any conflict."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "T")
    (repo / "a.py").write_text("base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "checkout", "-q", "-b", "upstream")
    (repo / "a.py").write_text("upstream\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "upstream")
    end = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "checkout", "-q", "main")
    return repo, base, end


def _run(repo, base, end, tmp_path, policy="{}"):
    policy_file = tmp_path / "policy.yml"
    policy_file.write_text(policy)
    report = tmp_path / "report.md"
    outputs = tmp_path / "outputs.txt"
    code = main(
        [
            "--repo", str(repo),
            "--base", base,
            "--end", end,
            "--policy", str(policy_file),
            "--report-file", str(report),
            "--github-output", str(outputs),
            "--skip-regeneration",
        ]
    )
    # A rejected policy stops before either file is written.
    return (
        code,
        report.read_text() if report.exists() else "",
        outputs.read_text() if outputs.exists() else "",
    )


def test_a_clean_batch_exits_zero(clean_fork, tmp_path):
    code, _, _ = _run(*clean_fork, tmp_path)

    assert code == 0


def test_a_clean_batch_reports_that_no_human_is_needed(clean_fork, tmp_path):
    _, _, outputs = _run(*clean_fork, tmp_path)

    assert "needs_human=false" in outputs


def test_a_clean_batch_writes_a_report_file(clean_fork, tmp_path):
    _, report, _ = _run(*clean_fork, tmp_path)

    assert "No manual steps" in report


def test_a_conflicted_batch_still_exits_zero(tmp_path):
    """A conflict is a reviewable outcome, not a workflow failure."""
    repo = tmp_path / "c"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "T")
    (repo / "a.py").write_text("base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "checkout", "-q", "-b", "upstream")
    (repo / "a.py").write_text("upstream\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "up")
    end = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "checkout", "-q", "main")
    (repo / "a.py").write_text("fork\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "fork")

    code, report, outputs = _run(repo, base, end, tmp_path)

    assert code == 0
    assert "needs_human=true" in outputs
    assert "a.py" in report


def test_a_malformed_policy_fails_loudly(clean_fork, tmp_path):
    """A broken policy must stop the run, not silently sync everything."""
    code, *_ = _run(*clean_fork, tmp_path, policy="nonsense_class: [a]")

    assert code != 0


def test_the_conflict_count_is_exposed_to_the_workflow(clean_fork, tmp_path):
    _, _, outputs = _run(*clean_fork, tmp_path)

    assert "conflict_count=0" in outputs
