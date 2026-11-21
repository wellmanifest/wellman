"""wellman advise: rules decide, oqllm/SubLLM only advise (ticket-114)."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from wellman import advise


def _git(path: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    return subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True, env=env).stdout


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / "a.txt").write_text("a")
    _git(root, "add", "a.txt")
    _git(root, "commit", "-q", "-m", "a")
    (root / ".subactor/leases").mkdir(parents=True)
    return root


def _lease(root: Path, wid: str, *, phase="claimed", heartbeat="2026-11-21T10:00:00Z", owner="agent:demo"):
    (root / ".subactor/leases" / f"{wid}.json").write_text(json.dumps(
        {"ticketId": wid.split("--")[0], "phase": phase, "ownerActor": owner, "heartbeatAt": heartbeat}))


def _worktree(root: Path, wid: str) -> Path:
    tree = root / ".worktrees" / wid
    tree.mkdir(parents=True)
    _git(tree, "init", "-q", "-b", "main")
    (tree / "a.txt").write_text("a")
    _git(tree, "add", "a.txt")
    _git(tree, "commit", "-q", "-m", "a")
    _git(tree, "update-ref", "refs/remotes/origin/main", "HEAD")
    return tree


NOW = 1_795_300_000.0  # 2026-11-21T~18:40Z


@pytest.fixture
def plans(monkeypatch):
    planned: set[str] = set()
    monkeypatch.setattr(advise, "_controller_plans_release", lambda root, ticket, runner: ticket in planned)
    monkeypatch.setattr(advise, "verified_classifier", lambda root: (lambda tree, entry: entry.rstrip("/") == ".venv"))
    return planned


def _decisions(root):
    return {a["subject"]: a for a in advise.lease_actions(root, now=NOW)}


def test_merged_lease_with_classified_runtime_state_is_settled(tmp_path, plans):
    root = _repo(tmp_path)
    _lease(root, "ticket-001--done")
    tree = _worktree(root, "ticket-001--done")
    (tree / ".git/info/exclude").write_text(".venv/\n")
    (tree / ".venv").mkdir()
    (tree / ".venv/x").write_text("x")
    plans.add("ticket-001")
    action = _decisions(root)["ticket-001"]
    assert action["decision"] == "settle" and "--settle-verified --ticket ticket-001 --apply" in action["next_step"]
    assert action["standard"] == "wellmanifest/new-project"


def test_unclassified_ignored_data_needs_owner_review(tmp_path, plans):
    root = _repo(tmp_path)
    _lease(root, "ticket-002--done")
    tree = _worktree(root, "ticket-002--done")
    (tree / ".git/info/exclude").write_text(".env\n")
    (tree / ".env").write_text("TOKEN_PLACEHOLDER=1")
    plans.add("ticket-002")
    action = _decisions(root)["ticket-002"]
    assert action["decision"] == "owner-review" and ".env" in action["next_step"]


def test_changes_or_unplanned_leases_are_kept(tmp_path, plans):
    root = _repo(tmp_path)
    _lease(root, "ticket-003--wip")
    (_worktree(root, "ticket-003--wip") / "new.txt").write_text("unpublished")
    plans.add("ticket-003")
    _lease(root, "ticket-004--open")
    _worktree(root, "ticket-004--open")
    decisions = _decisions(root)
    assert decisions["ticket-003"]["decision"] == "keep" and decisions["ticket-004"]["decision"] == "keep"


@pytest.mark.parametrize(("heartbeat", "decision"), [("2026-10-01T00:00:00Z", "owner-cancel-or-handoff"),
                                                     ("2026-11-21T18:00:00Z", "keep")])
def test_absent_worktree_is_handed_to_its_owner_only_when_stale(tmp_path, plans, heartbeat, decision):
    root = _repo(tmp_path)
    _lease(root, "ticket-005--gone", heartbeat=heartbeat, owner="agent:cline")
    action = _decisions(root)["ticket-005"]
    assert action["decision"] == decision


def test_released_leases_are_ignored_beyond_the_active_cap(tmp_path, plans, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setattr(advise, "MAX_LEASES", 1)
    _lease(root, "ticket-001--old", phase="released")
    _lease(root, "ticket-009--gone", heartbeat="2026-01-01T00:00:00Z")
    assert list(_decisions(root)) == ["ticket-009"]


def _open_item():
    return [{"id": "t-1", "kind": "lease", "subject": "ticket-1", "decision": "owner-review",
             "standard": "wellmanifest/worktrees", "rule": "r", "evidence": {}}]


def test_llm_advice_is_attached_without_changing_the_decision():
    def failing(messages, timeout):
        raise OSError("oqllm down")

    def subllm(messages, timeout):
        assert "untrusted evidence" in messages[0]["content"]
        reply = {"items": [{"id": "t-1", "classification": "unique-data", "suggestion": "archive first",
                            "reason": "secrets"}, {"id": "other", "suggestion": "ignored"}]}
        return "```json\n" + json.dumps(reply) + "\n```", "subllm", "m"

    actions = _open_item()
    result = advise.llm_advice(actions, transports=(failing, subllm))
    assert result == {"status": "advisory", "provider": "subllm", "model": "m", "items": 1}
    assert actions[0]["decision"] == "owner-review"
    assert actions[0]["llm_suggestion"]["classification"] == "unique-data" and actions[0]["llm_suggestion"]["advisory"]


def test_llm_is_not_called_when_rules_decide_everything():
    called = []
    actions = [{"id": "x", "kind": "lease", "subject": "s", "decision": "settle", "standard": "", "rule": "",
                "evidence": {}, "next_step": "n"}]
    assert advise.llm_advice(actions, transports=(lambda *a: called.append(a),)) == {"status": "not_needed"}
    assert called == []


def test_unavailable_llm_reports_without_failing():
    def broken(messages, timeout):
        raise ValueError("bad")
    assert advise.llm_advice(_open_item(), transports=(broken,))["status"] == "unavailable"


@pytest.mark.parametrize("url", ["https://127.0.0.1:11437", "http://10.0.0.5:11437", "http://127.0.0.1:11437/v1"])
def test_oqllm_endpoint_must_be_a_bare_loopback_origin(url):
    with pytest.raises(ValueError):
        advise._loopback(url)


def test_render_numbers_visible_steps_and_states_no_authority():
    advice = {"root": "/r", "summary": {"keep": 1, "settle": 1}, "llm": {"status": "disabled"},
              "authority": "none: review candidates; no command was executed",
              "actions": [{"decision": "keep", "subject": "k", "standard": "s", "rule": "r"},
                          {"decision": "settle", "subject": "ticket-1", "standard": "s", "rule": "r", "next_step": "cmd"}]}
    text = advise.render(advice)
    assert "1. [settle] ticket-1" in text and "[keep]" not in text and "no command was executed" in text


def test_urtlog_emission_is_opt_in(monkeypatch):
    monkeypatch.delenv("URTLOG_STATE_DIR", raising=False)
    assert advise.emit_urtlog({"actions": [], "summary": {}}, "demo") == {"emitted": False, "reason": "disabled"}
