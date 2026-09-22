"""The PR body that makes every automatic decision auditable."""

from scripts.upstream_sync.manifests import Decision
from scripts.upstream_sync.policy import PathClass
from scripts.upstream_sync.report import build_report


def test_a_clean_sync_says_so_plainly():
    report = build_report()

    assert "No manual steps" in report


def test_conflicted_files_are_listed_so_a_human_knows_where_to_look():
    report = build_report(conflicts=["boneio/webui/app.py", "frontend/vite.config.ts"])

    assert "boneio/webui/app.py" in report
    assert "frontend/vite.config.ts" in report


def test_fork_owned_drops_are_reported_rather_than_vanishing_silently():
    """Otherwise upstream's evolution of these files is lost without trace."""
    report = build_report(dropped={"CHANGELOG.md": PathClass.FORK_OWNED})

    assert "CHANGELOG.md" in report
    assert "fork_owned" in report


def test_regenerated_lockfiles_are_named():
    report = build_report(regenerated=["uv.lock"])

    assert "uv.lock" in report


def test_a_dependency_needing_review_is_called_out_prominently():
    decisions = {
        "pyproject.toml": [
            Decision("requests", "requests==2.34.2", "upstream downgrade", True),
            Decision("aiohttp", "aiohttp==3.14.3", "both sides agree", False),
        ]
    }

    report = build_report(manifest_decisions=decisions)

    assert "requests" in report
    assert "Needs review" in report


def test_dependencies_that_resolved_quietly_are_not_noise_in_the_summary():
    """"Both sides agree" is the common case and should not dominate the body."""
    decisions = {
        "pyproject.toml": [
            Decision(f"pkg{i}", f"pkg{i}==1.0", "both sides agree", False)
            for i in range(30)
        ]
    }

    report = build_report(manifest_decisions=decisions)

    assert "pkg0" not in report
    assert "30" in report


def test_a_changed_dependency_is_shown_even_when_it_needs_no_review():
    decisions = {
        "pyproject.toml": [
            Decision("PyJWT", "PyJWT==2.14.0", "upstream added it", False),
        ]
    }

    report = build_report(manifest_decisions=decisions)

    assert "PyJWT" in report
    assert "upstream added it" in report


def test_a_removed_dependency_is_shown_as_removed():
    decisions = {
        "pyproject.toml": [
            Decision("python-jose", None, "upstream removed it", False),
        ]
    }

    report = build_report(manifest_decisions=decisions)

    assert "python-jose" in report
    assert "removed" in report
