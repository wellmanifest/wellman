"""Tests for safe repository-fleet discovery and adoption."""

import json
import subprocess

from wellman import __version__
from wellman.fleet import (
    apply_plan,
    build_plan,
    discover_repositories,
    emit_standardization_tickets,
    feed_to_planfile,
    sync_agent_instructions,
    sync_fleet_agents,
)
from wellman.cli import main


def make_repository(parent, name, remote="git@github.com:acme/example.git"):
    path = parent / name
    path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "remote", "add", "origin", remote], cwd=path, check=True)
    return path


def test_discover_skips_hidden_git_directories(tmp_path):
    make_repository(tmp_path, "visible", "git@github.com:acme/visible.git")
    make_repository(tmp_path, ".hidden", "git@github.com:acme/hidden.git")

    assert discover_repositories(tmp_path) == [tmp_path / "visible"]


def test_fleet_plan_blocks_dirty_repository(tmp_path):
    repo = make_repository(tmp_path, "visible")
    (repo / "README.md").write_text("dirty\n", encoding="utf-8")

    plan = build_plan(tmp_path, "baseline")

    assert plan["blocked"] == 1
    assert plan["repositories"][0]["ready"] is False
    assert "working tree is dirty" in plan["repositories"][0]["blockers"]


def test_fleet_apply_creates_repository_bound_adoption(tmp_path):
    repo = make_repository(tmp_path, "visible", "https://github.com/acme/visible.git")
    plan = build_plan(tmp_path, "baseline")

    result = apply_plan(plan, "baseline")

    assert result["repositories"][0]["status"] == "updated"
    manifest = json.loads((repo / ".governance/manifest.json").read_text(encoding="utf-8"))
    docs = json.loads((repo / ".governance/docs.json").read_text(encoding="utf-8"))
    assert manifest["standard"] == {"id": "profile:baseline", "version": __version__}
    assert docs["repository"] == "acme/visible"


def test_fleet_manifest_update_preserves_custom_fields(tmp_path):
    repo = make_repository(tmp_path, "visible")
    gov = repo / ".governance"
    gov.mkdir()
    (gov / "manifest.json").write_text(
        json.dumps({
            "schema": "new-project.governance/v2",
            "standard": {"id": "wellmanifest/new-project", "version": "0.20.32"},
            "custom": {"keep": True},
        }),
        encoding="utf-8",
    )

    plan = build_plan(tmp_path, "baseline", allow_dirty=True, update_manifests=True)
    apply_plan(plan, "baseline", update_manifests=True)
    updated = json.loads((gov / "manifest.json").read_text(encoding="utf-8"))

    assert updated["standard"]["version"] == __version__
    assert updated["custom"] == {"keep": True}


def test_emit_standardization_tickets_empty():
    report = {
        "schema": "wellman.fleet-report/v1",
        "repositories": [{"path": "/path/repo", "repository": "org/repo", "findings": []}],
    }
    result = emit_standardization_tickets(report)
    assert result["schema"] == "planfile.tickets/v1"
    assert result["count"] == 0
    assert result["tickets"] == []


def test_emit_standardization_tickets_with_findings():
    report = {
        "schema": "wellman.fleet-report/v1",
        "repositories": [
            {
                "path": "/path/to/repo-a",
                "repository": "org/repo-a",
                "findings": [
                    {
                        "code": "GOV-MANIFEST-MISSING",
                        "severity": "ERROR",
                        "message": "Missing .governance/manifest.json",
                        "remediation": "Run wellman adopt baseline",
                    },
                    {
                        "code": "GOV-WORKTREE-OVERLAP",
                        "severity": "WARNING",
                        "message": "Active worktree overlap detected",
                        "remediation": "Prune stale worktrees",
                    },
                ],
            }
        ],
    }
    result = emit_standardization_tickets(report, koru_ready=True)
    assert result["schema"] == "planfile.tickets/v1"
    assert result["count"] == 1
    ticket = result["tickets"][0]
    assert "[STANDARDIZATION]" in ticket["title"]
    assert ticket["name"] == ticket["title"]
    assert "repo-a" in ticket["title"]
    assert ticket["priority"] == "critical"
    assert ticket["tier"] == "floor"
    assert "wellmanifest" in ticket["labels"]
    assert "koru-refactor" in ticket["labels"]
    assert "governance-handoff" in ticket["labels"]
    assert ticket["source"] == {"tool": "wellman"}
    assert ticket["executor"]["kind"] == "shell"
    assert "script" in ticket["inputs"]
    assert ticket["execution"]["queue"] == "governance-handoff"
    assert ticket["execution"]["state"] == "ready"
    assert ticket["executor_kind"] == "koru"
    assert ticket["remediation_intent"]["schema"] == "new-project.remediation-intent/v1"
    assert len(ticket["remediation_intent"]["findings"]) == 2


def test_fleet_check_cli_emit_planfile(tmp_path, capsys):
    make_repository(tmp_path, "subrepo", "https://github.com/acme/subrepo.git")
    out_file = tmp_path / "planfile-tickets.json"

    # subrepo is missing governance files, so findings will be detected
    ret = main(["fleet", "check", "--root", str(tmp_path), "--emit-planfile", str(out_file), "--koru-handoff"])
    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["schema"] == "planfile.tickets/v1"
    assert data["count"] >= 1
    assert data["tickets"][0]["executor_kind"] == "koru"


def test_discover_repositories_contextual_auto_recursive(tmp_path):
    org_a = tmp_path / "org_a"
    org_b = tmp_path / "org_b"
    org_a.mkdir()
    org_b.mkdir()
    repo_1 = make_repository(org_a, "repo_1", "https://github.com/org_a/repo_1.git")
    repo_2 = make_repository(org_b, "repo_2", "https://github.com/org_b/repo_2.git")

    # When run on tmp_path (which has no direct .git repos, only org dirs),
    # contextual auto-discovery should find both nested repositories automatically.
    discovered = discover_repositories(tmp_path)
    assert repo_1 in discovered
    assert repo_2 in discovered
    assert len(discovered) == 2

    # With explicit recursive=False, it strictly returns direct children (0).
    assert discover_repositories(tmp_path, recursive=False) == []


def test_sync_agent_instructions(tmp_path):
    repo = make_repository(tmp_path, "ai_repo", "https://github.com/acme/ai_repo.git")
    updated = sync_agent_instructions(repo)

    assert "AGENTS.md" in updated
    assert "GEMINI.md" in updated
    assert "CLAUDE.md" in updated
    assert ".cursor/rules/new-project-standard.mdc" in updated
    assert ".github/copilot-instructions.md" in updated
    assert ".aider.conf.yml" in updated

    assert (repo / "AGENTS.md").is_file()
    assert (repo / "GEMINI.md").is_file()
    assert (repo / "CLAUDE.md").is_file()
    assert (repo / ".cursor/rules/new-project-standard.mdc").is_file()
    assert (repo / ".github/copilot-instructions.md").is_file()
    assert (repo / ".aider.conf.yml").is_file()

    gemini_content = (repo / "GEMINI.md").read_text(encoding="utf-8")
    assert "new-project" in gemini_content
    assert "new-ticket.sh" in gemini_content


def test_fleet_sync_agents_cli(tmp_path, capsys):
    org = tmp_path / "org"
    org.mkdir()
    repo = make_repository(org, "repo", "https://github.com/acme/repo.git")

    ret = main(["fleet", "sync-agents", "--root", str(tmp_path), "--json"])
    assert ret == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["schema"] == "wellman.fleet-agent-sync/v1"
    assert payload["synchronized_count"] >= 1
    assert (repo / "GEMINI.md").is_file()


def test_fleet_discover_cli_text_output(tmp_path, capsys):
    org = tmp_path / "org"
    org.mkdir()
    repo = make_repository(org, "repo", "https://github.com/acme/repo.git")

    ret = main(["fleet", "discover", "--root", str(tmp_path)])
    assert ret == 0
    captured = capsys.readouterr()
    assert str(repo) in captured.out


def test_feed_to_planfile_pipes_array(monkeypatch, tmp_path):
    from wellman.fleet import feed_to_planfile
    captured_stdin = []

    def fake_run(cmd, input=None, cwd=None, **kwargs):
        captured_stdin.append(input)
        class Dummy:
            returncode = 0
            stdout = "✓ Created 1 tickets"
            stderr = ""
        return Dummy()

    monkeypatch.setattr("shutil.which", lambda prog: "/bin/planfile")
    monkeypatch.setattr("subprocess.run", fake_run)

    tickets_doc = {
        "schema": "planfile.tickets/v1",
        "tickets": [
            {
                "name": "test ticket",
                "target_path": str(tmp_path),
                "executor": {"kind": "shell"},
            }
        ],
    }

    res = feed_to_planfile(tickets_doc, planfile_project=tmp_path, per_repo=False)
    assert res["ok"] is True
    assert len(captured_stdin) == 1
    loaded = json.loads(captured_stdin[0])
    assert isinstance(loaded, list)
    assert loaded[0]["name"] == "test ticket"


def test_trigger_koru_execution(monkeypatch, tmp_path):
    from wellman.fleet import trigger_koru_execution
    ran_cmds = []

    def fake_run(cmd, **kwargs):
        ran_cmds.append(cmd)
        class Dummy:
            returncode = 0
            stdout = "koru completed"
            stderr = ""
        return Dummy()

    monkeypatch.setattr("shutil.which", lambda prog: "/bin/koru")
    monkeypatch.setattr("subprocess.run", fake_run)

    res = trigger_koru_execution(tmp_path, queue_name="governance-handoff", dry_run=True)
    assert res["ok"] is True
    assert len(ran_cmds) == 1
    assert "koru" in ran_cmds[0]
    assert "--queue-name" in ran_cmds[0]
    assert "governance-handoff" in ran_cmds[0]
    assert "--dry-run" in ran_cmds[0]


def test_fleet_check_cli_auto_remediate(monkeypatch, tmp_path, capsys):
    make_repository(tmp_path, "subrepo", "https://github.com/acme/subrepo.git")

    monkeypatch.setattr("shutil.which", lambda prog: f"/bin/{prog}")

    def fake_run(cmd, input=None, cwd=None, **kwargs):
        class Dummy:
            returncode = 0
            stdout = "ok"
            stderr = ""
        return Dummy()

    monkeypatch.setattr("subprocess.run", fake_run)

    ret = main(["fleet", "check", "--root", str(tmp_path), "--auto-remediate"])
    captured = capsys.readouterr()
    assert "Fed" in captured.out or "Triggering autonomous Koru remediation" in captured.out




def test_fleet_apply_writes_local_ci_default_and_keeps_restrictions(tmp_path):
    open_repo = make_repository(tmp_path, "open", "https://github.com/acme/open.git")
    narrowed = make_repository(tmp_path, "narrowed", "https://github.com/acme/narrowed.git")
    restriction = {"schema": "new-project.local-ci-publication/v1",
                   "scope": {"mode": "restricted", "repositories": ["acme/narrowed"]}}
    (narrowed / ".governance").mkdir()
    (narrowed / ".governance/local-ci-publication.json").write_text(json.dumps(restriction), encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=narrowed, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"], cwd=narrowed, check=True)

    result = apply_plan(build_plan(tmp_path, "baseline"), "baseline")

    by_name = {item["repository"]: item for item in result["repositories"]}
    assert by_name["acme/open"]["local_ci_publication"] == "created"
    assert "local_ci_publication" not in by_name["acme/narrowed"]
    assert json.loads((open_repo / ".governance/local-ci-publication.json").read_text()) == {
        "schema": "new-project.local-ci-publication/v1", "scope": {"mode": "all"}}
    assert json.loads((narrowed / ".governance/local-ci-publication.json").read_text()) == restriction
