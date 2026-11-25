"""The bundled resolver must accept the policies new-project ships.

The overlap and governance checkers bundled with Wellman resolve every checkout
with this copy. A copy older than the standard rejects a policy that lists a
newer verification kind ("managed terminal outcome rule is unsupported"), which
fails `wellman check` for every checkout of an adopter.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

BUNDLED = Path(__file__).resolve().parents[1] / "src" / "wellman" / "_bundled"
sys.path.insert(0, str(BUNDLED))
import ticket_activity as ta  # noqa: E402

BASE_POLICY = {
    "$schema": "./ticket-activity.schema.json",
    "schema": "new-project.ticket-activity/v1",
    "registry": {"location": "git-common-dir", "path": "new-project/terminal-receipts.json",
                 "missingPolicy": "status-projection"},
    "terminalOutcomes": {
        "merged": {"verification": "git-ancestry-or-rewritten-patch-series", "releasesReservation": True},
        "no-change": {"verification": "git-ancestry", "releasesReservation": True},
        "cancelled": {"verification": "owner-decision", "releasesReservation": True},
    },
    "unsupportedOutcomePolicy": "remain-active",
}


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "repo"
    _git(tmp_path, "init", "--quiet", "--initial-branch=main", str(root))
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / ".governance").mkdir()
    (root / ".governance/ticket-activity.json").write_text(json.dumps(BASE_POLICY))
    (root / "README.md").write_text("base\n")
    _git(root, "add", ".")
    _git(root, "commit", "--quiet", "-m", "base")
    _git(root, "switch", "--quiet", "-c", "ticket/002-rejected")
    (root / "project/ticket-002").mkdir(parents=True)
    (root / "project/ticket-002/README.md").write_text("- **Status**: IN_PROGRESS\n")
    (root / "work.txt").write_text("rejected\n")
    _git(root, "add", ".")
    _git(root, "commit", "--quiet", "-m", "rejected")
    head = _git(root, "rev-parse", "HEAD")
    _git(root, "switch", "--quiet", "main")
    terminal = _git(root, "rev-parse", "HEAD")
    _git(root, "switch", "--quiet", "ticket/002-rejected")
    return root, head, terminal


def test_policy_with_owner_decision_outcome_loads():
    ta._validate_terminal_outcomes(BASE_POLICY)


def test_cancelled_receipt_releases_and_resumed_work_reactivates(repo):
    root, head, terminal = repo
    ticket_dir = root / "project/ticket-002"
    assert ta.resolve(root, ticket_dir, {"IN_PROGRESS"}).active is True
    ta.record(root, {
        "receiptRef": "receipt:test/cancel/1", "ticket": "ticket-002", "outcome": "cancelled",
        "headSha": head, "terminalSha": terminal, "targetBranch": "main",
        "occurredAt": "2026-11-23T12:00:00Z",
        "decision": {"pullRequest": 7, "pullRequestState": "closed-unmerged",
                     "decidedBy": "owner", "decisionRef": "https://example.invalid/pull/7"},
    })
    released = ta.resolve(root, ticket_dir, {"IN_PROGRESS"})
    assert released.active is False and released.authority == "terminal-receipt"
    (root / "work.txt").write_text("resumed\n")
    _git(root, "commit", "--quiet", "-am", "resumed")
    assert ta.resolve(root, ticket_dir, {"IN_PROGRESS"}).active is True


def test_cancelled_receipt_without_decision_is_refused(repo):
    root, head, terminal = repo
    with pytest.raises(ta.ActivityError):
        ta.record(root, {
            "receiptRef": "receipt:test/cancel/2", "ticket": "ticket-002", "outcome": "cancelled",
            "headSha": head, "terminalSha": terminal, "targetBranch": "main",
            "occurredAt": "2026-11-23T12:00:00Z",
        })
