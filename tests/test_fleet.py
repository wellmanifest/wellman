"""Tests for safe repository-fleet discovery and adoption."""

import hashlib
import json

import pytest
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
    trigger_taskand_execution,
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


def test_fleet_plan_discloses_all_additive_recovery_effects(tmp_path):
    repo = make_repository(tmp_path, "visible")
    actions = build_plan(repo, "wellmanifest/merge")["repositories"][0]["actions"]
    assert "create .governance/local-ci-publication.json" in actions
    assert "create .governance/standard-packs.json" in actions
    assert "register .governance/standard-requirements.json" in actions
    hosts = next(action for action in actions if action.startswith("project agent host"))
    for name in ("AGENTS.md", "GEMINI.md", "CLAUDE.md", ".aider.conf.yml",
                 ".cursor/rules/new-project-standard.mdc", ".github/copilot-instructions.md"):
        assert name in hosts


@pytest.mark.parametrize("change", ["policy", "host", "origin", "dirty"])
def test_fleet_rejects_changed_plan_before_any_writes(tmp_path, change):
    repo = make_repository(tmp_path, "visible")
    plan = build_plan(repo, "wellmanifest/merge")
    if change == "policy":
        (repo / ".governance").mkdir()
        (repo / ".governance/local-ci-publication.json").write_text(json.dumps({
            "schema": "new-project.local-ci-publication/v1",
            "scope": {"mode": "restricted", "repositories": ["acme/*"]},
        }))
    elif change == "origin":
        subprocess.run(["git", "remote", "set-url", "origin", "https://github.com/other/repo.git"], cwd=repo, check=True)
    else:
        (repo / ("AGENTS.md" if change == "host" else "unknown.txt")).write_text("preserve\n")
    before = {p.relative_to(repo): p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    result = apply_plan(plan, "wellmanifest/merge")
    assert result["repositories"][0]["status"] == "skipped"
    assert "fleet plan is stale" in " ".join(result["repositories"][0]["blockers"])
    assert {p.relative_to(repo): p.read_bytes() for p in repo.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("unsafe", ["invalid", "policy-symlink", "governance-symlink", "packs-symlink"])
def test_fleet_recovery_policy_problems_block_all_writes(tmp_path, unsafe):
    repo = make_repository(tmp_path, "visible")
    outside = tmp_path / "outside"
    outside.mkdir()
    if unsafe == "governance-symlink":
        (repo / ".governance").symlink_to(outside, target_is_directory=True)
    else:
        (repo / ".governance").mkdir()
        policy = repo / ".governance/local-ci-publication.json"
        if unsafe == "invalid":
            policy.write_text('{"scope": "broken"}')
        elif unsafe == "policy-symlink":
            policy.symlink_to(outside / "missing")
        else:
            (repo / ".governance/standard-packs.json").symlink_to(outside / "missing")
    plan = build_plan(repo, "wellmanifest/merge", allow_dirty=True)
    assert plan["blocked"] == 1
    assert apply_plan(plan, "wellmanifest/merge")["repositories"][0]["status"] == "skipped"
    assert not (repo / ".governance/manifest.json").exists()
    assert not (repo / "AGENTS.md").exists()
    assert list(outside.iterdir()) == []


def test_fleet_rejects_target_substitution(tmp_path):
    repo = make_repository(tmp_path, "visible")
    plan = build_plan(repo, "wellmanifest/merge")
    with pytest.raises(ValueError, match="target does not match"):
        apply_plan(plan, "baseline")
    assert not (repo / ".governance").exists()


def test_fleet_noop_preserves_policy_docs_and_locks(tmp_path):
    repo = make_repository(tmp_path, "visible")
    apply_plan(build_plan(repo, "baseline"), "baseline")
    plan = build_plan(repo, "baseline", allow_dirty=True)
    assert plan["repositories"][0]["actions"] == []
    before = {p.relative_to(repo): (p.read_bytes(), p.stat().st_mtime_ns)
              for p in repo.rglob("*") if p.is_file()}
    assert apply_plan(plan, "baseline")["repositories"][0]["status"] == "up-to-date"
    assert {p.relative_to(repo): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in repo.rglob("*") if p.is_file()} == before


def test_fleet_registers_merge_requirement_without_replacing_native_pins(tmp_path):
    repo = make_repository(tmp_path, "native")
    governance = repo / ".governance"
    governance.mkdir()
    manifest = governance / "manifest.json"
    original = '{"schema":"new-project.governance/v2","standard":{"id":"wellmanifest/new-project","version":"0.20.80"}}\n'
    manifest.write_text(original)
    result = apply_plan(build_plan(repo, "wellmanifest/merge", allow_dirty=True), "wellmanifest/merge")
    requirements = json.loads((governance / "standard-requirements.json").read_text())
    assert "wellmanifest/merge" in {item["id"] for item in requirements["requirements"]}
    assert "wellmanifest/validation-attestation" in {item["id"] for item in requirements["requirements"]}
    assert result["repositories"][0]["conformance"] == "unverified"
    assert manifest.read_text() == original


def test_fleet_does_not_overwrite_malformed_requirements(tmp_path):
    repo = make_repository(tmp_path, "native")
    (repo / ".governance").mkdir()
    requirements = repo / ".governance/standard-requirements.json"
    requirements.write_text('{"schema":"unknown"}')
    plan = build_plan(repo, "wellmanifest/merge", allow_dirty=True)
    assert plan["blocked"] == 1
    assert apply_plan(plan, "wellmanifest/merge")["repositories"][0]["status"] == "skipped"
    assert requirements.read_text() == '{"schema":"unknown"}'
    assert not (repo / ".governance/local-ci-publication.json").exists()


def test_fleet_apply_creates_repository_bound_adoption(tmp_path):
    repo = make_repository(tmp_path, "visible", "https://github.com/acme/visible.git")
    plan = build_plan(tmp_path, "baseline")

    result = apply_plan(plan, "baseline")

    assert result["repositories"][0]["status"] == "updated"
    manifest = json.loads((repo / ".governance/manifest.json").read_text(encoding="utf-8"))
    docs = json.loads((repo / ".governance/docs.json").read_text(encoding="utf-8"))
    assert manifest["standard"] == {"id": "profile:baseline", "version": __version__}
    assert docs["repository"] == "acme/visible"



@pytest.mark.parametrize("package_mapped", [False, True])
@pytest.mark.parametrize("docs_tracked", [False, True])
def test_fleet_docs_adoption_preserves_package_lock_ownership(
    tmp_path, package_mapped, docs_tracked
):
    repo = make_repository(tmp_path, "visible", "https://github.com/acme/visible.git")
    gov = repo / ".governance"
    gov.mkdir()
    (gov / "manifest.json").write_text(json.dumps({
        "schema": "new-project.governance/v2",
        "standard": {"id": "wellmanifest/new-project", "version": "0.20.80"},
    }))
    managed = {"AGENTS.md": "a" * 64}
    if docs_tracked:
        managed[".governance/docs.json"] = "b" * 64
    lock = {"schema": "new-project.adoption-lock/v1", "managedFiles": managed}
    lock_path = gov / "manifest.lock.json"
    original = json.dumps(lock, indent=4) + "\n"
    lock_path.write_text(original, encoding="utf-8")
    if package_mapped:
        (gov / "package-manifest.json").write_text(
            json.dumps({"schema": "new-project.package-manifest/v1", "files": [
                {"target": name, "strategy": "managed"} for name in managed
            ]}), encoding="utf-8"
        )

    plan = build_plan(repo, "baseline", allow_dirty=True)
    refresh = "refresh docs.json digest in manifest.lock.json"
    assert (refresh in plan["repositories"][0]["actions"]) == (
        docs_tracked and not package_mapped
    )
    apply_plan(plan, "baseline", sync_agents=False)

    updated = json.loads(lock_path.read_text(encoding="utf-8"))
    assert set(updated["managedFiles"]) == set(managed)
    assert updated["managedFiles"]["AGENTS.md"] == "a" * 64
    if package_mapped or not docs_tracked:
        assert lock_path.read_text(encoding="utf-8") == original
    else:
        assert updated["managedFiles"][".governance/docs.json"] == hashlib.sha256(
            (gov / "docs.json").read_bytes()
        ).hexdigest()
    assert json.loads((gov / "docs.json").read_text())["repository"] == "acme/visible"



def test_fleet_preserves_lock_with_dangling_package_map(tmp_path):
    repo = make_repository(tmp_path, "visible")
    gov = repo / ".governance"
    gov.mkdir()
    (gov / "manifest.json").write_text(json.dumps({
        "schema": "new-project.governance/v2",
        "standard": {"id": "wellmanifest/new-project", "version": "0.20.80"},
    }))
    (gov / "package-manifest.json").symlink_to("missing-package.json")
    lock_path = gov / "manifest.lock.json"
    original = json.dumps({"managedFiles": {".governance/docs.json": "a" * 64}})
    lock_path.write_text(original, encoding="utf-8")
    plan = build_plan(repo, "baseline", allow_dirty=True)
    assert "refresh docs.json digest in manifest.lock.json" not in plan["repositories"][0]["actions"]
    apply_plan(plan, "baseline", sync_agents=False)
    assert lock_path.read_text(encoding="utf-8") == original



def test_fleet_non_docs_target_leaves_docs_lock_untouched(tmp_path):
    repo = make_repository(tmp_path, "visible")
    gov = repo / ".governance"
    gov.mkdir()
    (gov / "manifest.json").write_text(json.dumps({
        "schema": "new-project.governance/v2",
        "standard": {"id": "wellmanifest/new-project", "version": "0.20.80"},
    }))
    lock_path = gov / "manifest.lock.json"
    original = json.dumps({"managedFiles": {".governance/docs.json": "a" * 64}})
    lock_path.write_text(original, encoding="utf-8")
    plan = build_plan(repo, "wellmanifest/worktrees", allow_dirty=True)
    apply_plan(plan, "wellmanifest/worktrees", sync_agents=False)
    assert lock_path.read_text(encoding="utf-8") == original
    assert not (gov / "docs.json").exists()


def test_fleet_manifest_update_preserves_custom_fields(tmp_path):
    repo = make_repository(tmp_path, "visible")
    gov = repo / ".governance"
    gov.mkdir()
    (gov / "manifest.json").write_text(
        json.dumps({
            "schema": "wellmanifest.manifest/v1",
            "standard": {"id": "profile:baseline", "version": "0.20.32"},
            "custom": {"keep": True},
        }),
        encoding="utf-8",
    )

    plan = build_plan(tmp_path, "baseline", allow_dirty=True, update_manifests=True)
    apply_plan(plan, "baseline", update_manifests=True)
    updated = json.loads((gov / "manifest.json").read_text(encoding="utf-8"))

    assert updated["standard"]["version"] == __version__
    assert updated["custom"] == {"keep": True}


@pytest.mark.parametrize("schema", ["new-project.governance/v2", "new-project.governance/v3"])
@pytest.mark.parametrize("locked", [False, True])
def test_fleet_rejects_native_version_updates_before_writes(tmp_path, schema, locked):
    repo = make_repository(tmp_path, "native")
    gov = repo / ".governance"
    gov.mkdir()
    manifest = gov / "manifest.json"
    manifest.write_text(json.dumps({
        "schema": schema,
        "standard": {"id": "wellmanifest/new-project", "version": "0.20.80"},
        "standards": [{"id": "wellmanifest/new-project", "version": "0.20.80"}],
    }) + "\n")
    if locked:
        (gov / "manifest.lock.json").write_text('{"managedFiles": {}}\n')
    before = {p.relative_to(repo): p.read_bytes() for p in gov.iterdir()}

    plan = build_plan(repo, "baseline", allow_dirty=True, update_manifests=True)
    result = apply_plan(plan, "baseline", update_manifests=True)

    assert plan["blocked"] == 1
    assert "pinned new-project" in " ".join(plan["repositories"][0]["blockers"])
    assert result["repositories"][0]["status"] == "skipped"
    assert {p.relative_to(repo): p.read_bytes() for p in gov.iterdir()} == before
    assert not (repo / "AGENTS.md").exists()


@pytest.mark.parametrize("partial", [False, True])
def test_fleet_rechecks_native_adoption_when_applying_stale_plan(tmp_path, partial):
    repo = make_repository(tmp_path, "native")
    plan = build_plan(repo, "baseline", update_manifests=True)
    assert plan["ready"] == 1
    gov = repo / ".governance"
    gov.mkdir()
    if not partial:
        (gov / "manifest.json").write_text(json.dumps({
            "schema": "new-project.governance/v2",
            "standard": {"id": "wellmanifest/new-project", "version": "0.20.80"},
        }) + "\n")
    (gov / "manifest.lock.json").write_text('{"managedFiles": {}}\n')
    before = {p.relative_to(repo): p.read_bytes() for p in gov.iterdir()}

    result = apply_plan(plan, "baseline", update_manifests=True)

    assert result["repositories"][0]["status"] == "skipped"
    assert result["repositories"][0]["ready"] is False
    assert "pinned new-project" in " ".join(result["repositories"][0]["blockers"])
    assert {p.relative_to(repo): p.read_bytes() for p in gov.iterdir()} == before
    assert not (repo / "AGENTS.md").exists()


@pytest.mark.parametrize("update_manifests", [False, True])
def test_fleet_does_not_create_scaffold_over_partial_lock(tmp_path, update_manifests):
    repo = make_repository(tmp_path, "partial")
    gov = repo / ".governance"
    gov.mkdir()
    lock = gov / "manifest.lock.json"
    lock.write_text('{"managedFiles": {}}\n')
    before = lock.read_bytes()

    plan = build_plan(repo, "baseline", allow_dirty=True, update_manifests=update_manifests)
    result = apply_plan(plan, "baseline", update_manifests=update_manifests)

    assert plan["blocked"] == 1
    assert result["repositories"][0]["status"] == "skipped"
    assert list(gov.iterdir()) == [lock]
    assert lock.read_bytes() == before


def test_fleet_additive_adoption_preserves_native_headers(tmp_path):
    repo = make_repository(tmp_path, "native")
    gov = repo / ".governance"
    gov.mkdir()
    manifest = gov / "manifest.json"
    original = json.dumps({
        "schema": "new-project.governance/v2",
        "standard": {"id": "wellmanifest/new-project", "version": "0.20.80"},
    }, indent=4) + "\n"
    manifest.write_text(original)
    lock = gov / "manifest.lock.json"
    lock.write_text('{"managedFiles": {}}\n')

    plan = build_plan(repo, "baseline", allow_dirty=True)
    result = apply_plan(plan, "baseline", sync_agents=False)

    assert result["repositories"][0]["status"] == "updated"
    assert manifest.read_text() == original
    assert lock.read_text() == '{"managedFiles": {}}\n'


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
    assert result["count"] == 3
    # Parent ticket is the last one appended, subtasks are 0 and 1
    subtask_remed = result["tickets"][0]
    subtask_cicd = result["tickets"][1]
    ticket = result["tickets"][2]

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
    assert "git" in ticket["inputs"]["script"]
    assert ticket["execution"]["queue"] == "governance-handoff"
    assert ticket["execution"]["state"] == "ready"
    assert ticket["executor_kind"] == "koru"
    assert ticket["remediation_intent"]["schema"] == "new-project.remediation-intent/v1"
    assert len(ticket["remediation_intent"]["findings"]) == 2
    assert "strategy" in ticket
    assert "phases" in ticket["strategy"]
    assert len(ticket["children"]) == 2

    # Check subtasks
    assert subtask_remed["parent"] == ticket["id"]
    assert "subtask:remediation" in subtask_remed["labels"]
    assert subtask_cicd["parent"] == ticket["id"]
    assert subtask_cicd["blocked_by"] == [subtask_remed["id"]]
    assert "subtask:cicd" in subtask_cicd["labels"]


def test_emit_standardization_tickets_with_taskand():
    report = {
        "schema": "wellman.fleet-report/v1",
        "repositories": [
            {
                "path": "/path/to/repo-taskand",
                "repository": "org/repo-taskand",
                "findings": [
                    {
                        "code": "GOV-MANIFEST-MISSING",
                        "severity": "ERROR",
                        "message": "Missing .governance/manifest.json",
                    },
                ],
            }
        ],
    }
    result = emit_standardization_tickets(report, taskand_ready=True)
    assert result["schema"] == "planfile.tickets/v1"
    assert result["count"] == 3
    ticket = result["tickets"][2]
    assert ticket["executor_kind"] == "taskand"
    assert "taskand-refactor" in ticket["labels"]
    assert "taskand-job" in ticket["labels"]
    assert "taskand" in ticket
    assert ticket["taskand"]["operation"] == "git.commit"


def test_trigger_taskand_execution(tmp_path):
    repo = make_repository(tmp_path, "target_repo", "https://github.com/acme/target_repo.git")
    res = trigger_taskand_execution(repo, dry_run=True)
    assert res["ok"] is True
    assert res["dry_run"] is True
    assert "operations_planned" in res


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


def test_fleet_check_cli_taskand_handoff(tmp_path, capsys):
    make_repository(tmp_path, "subrepo_tkd", "https://github.com/acme/subrepo_tkd.git")
    out_file = tmp_path / "planfile-taskand-tickets.json"

    ret = main(["fleet", "check", "--root", str(tmp_path), "--emit-planfile", str(out_file), "--taskand-handoff"])
    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["schema"] == "planfile.tickets/v1"
    assert data["count"] >= 1
    # Check that tickets use taskand executor
    assert data["tickets"][0]["executor_kind"] == "taskand"


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


def _selection_export_fixture(tmp_path):
    from wellman.applicability import build_catalog
    from wellman.selection_plan import capture_repository, compose_selection_plan

    source = make_repository(
        tmp_path, "selection-source", "https://github.com/acme/selection.git"
    )
    (source / "package.json").write_text('{"name":"demo","version":"1.0.0"}')
    (source / "demo.py").write_text("value=1\n")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "Fixture"], check=True)
    bundle = capture_repository(source)
    catalog = build_catalog(
        {"wellmanifest/new-project": "a" * 40},
        revision="b" * 40,
        trusted_source="test pins",
        metadata={
            "wellmanifest/new-project": {
                "managed_files": ["AGENTS.md"],
                "validators": ["review contract"],
            }
        },
    )
    plan = compose_selection_plan(bundle["observation"], catalog, bundle["adoptions"])
    context = {
        "observation": bundle["observation"],
        "catalog": catalog,
        "adoptions": bundle["adoptions"],
        "repository_roots": {"acme/selection": source},
    }
    target = tmp_path / "review-backlog"
    target.mkdir()
    return source, target, plan, context


def test_selection_export_requires_explicit_context_and_preserves_source(tmp_path):
    source, target, plan, context = _selection_export_fixture(tmp_path)
    before = {
        p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()
    }
    assert not feed_to_planfile(plan, target)["ok"]
    assert not (target / ".planfile").exists()
    pytest.importorskip("planfile.core.store")
    result = feed_to_planfile(plan, target, selection_context=context)
    assert result["ok"] and not result["remote_effects"] and not result["executable"]
    assert {
        p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()
    } == before


def test_selection_export_native_ids_dedupe_and_no_autonomous_execution(tmp_path):
    Store = pytest.importorskip("planfile.core.store").Store
    _, target, plan, context = _selection_export_fixture(tmp_path)
    first = feed_to_planfile(plan, target, selection_context=context)
    assert first["ok"] and first["created"] == len(plan["decisions"])
    store = Store(target)
    tickets = store.list_tickets(sprint="all")
    revisions = {t.id: t.updated_at for t in tickets}
    second = feed_to_planfile(plan, target, selection_context=context)
    assert second["ok"] and second["created"] == 0
    assert all(r["state"] == "reused" for r in second["tickets"])
    assert {t.id: t.updated_at for t in store.list_tickets(sprint="all")} == revisions
    for t in tickets:
        assert t.id.startswith("PLF-") and t.sprint == "backlog"
        assert (t.executor.kind, t.executor.mode) == ("human", "interactive")
        assert t.execution.state == "pending" and "actor:human" in t.labels
        assert t.inputs is None
    assert not (target / ".planfile/sync").exists()


@pytest.mark.parametrize("terminal", ["done", "canceled", "failed", "blocked"])
def test_selection_export_preserves_terminal_key_without_reopening(tmp_path, terminal):
    Store = pytest.importorskip("planfile.core.store").Store
    _, target, plan, context = _selection_export_fixture(tmp_path)
    first = feed_to_planfile(plan, target, selection_context=context)
    assert first["ok"]
    store = Store(target)
    t = store.get_ticket(first["tickets"][0]["id"])
    t = store.update_ticket(
        t.id,
        status=terminal,
        execution={"state": terminal},
        expected_updated_at=t.updated_at.isoformat(),
    )
    before = t.model_dump(mode="json")
    second = feed_to_planfile(plan, target, selection_context=context)
    assert second["ok"] and second["created"] == 0
    assert (
        next(r for r in second["tickets"] if r["id"] == t.id)["state"]
        == "preserved_terminal"
    )
    assert store.get_ticket(t.id).model_dump(mode="json") == before


def test_selection_export_uses_actual_dependency_ids(tmp_path):
    Store = pytest.importorskip("planfile.core.store").Store
    from wellman.applicability import build_catalog
    from wellman.selection_plan import compose_selection_plan

    _, target, _, context = _selection_export_fixture(tmp_path)
    ids = ["wellmanifest/new-project", "wellmanifest/docs"]
    context["catalog"] = build_catalog(
        {id: "a" * 40 for id in ids},
        revision="b" * 40,
        trusted_source="test",
        metadata={
            id: {
                "managed_files": ["AGENTS.md"],
                "validators": ["review contract"],
                "depends_on": []
                if id == ids[0]
                else [{"id": ids[0], "revisions": ["a" * 40]}],
            }
            for id in ids
        },
    )
    plan = compose_selection_plan(
        context["observation"], context["catalog"], context["adoptions"]
    )
    result = feed_to_planfile(plan, target, selection_context=context)
    assert result["ok"]
    tickets = Store(target).list_tickets(sprint="all")
    by_standard = {t.source.context["proposal"]["standard_id"]: t for t in tickets}
    assert by_standard[ids[1]].blocked_by == [by_standard[ids[0]].id]


def test_selection_export_rechecks_cas_and_preserves_owned_ticket(
    tmp_path, monkeypatch
):
    module = pytest.importorskip("planfile.core.store")
    Store = module.Store
    from wellman.selection_plan import compose_selection_plan

    _, target, plan, context = _selection_export_fixture(tmp_path)
    first = feed_to_planfile(plan, target, selection_context=context)
    assert first["ok"]
    store = Store(target)
    t = store.get_ticket(first["tickets"][0]["id"])
    store.update_ticket(
        t.id,
        executor={"kind": "shell", "mode": "automatic"},
        execution={"state": "running"},
        expected_updated_at=t.updated_at.isoformat(),
    )
    second = feed_to_planfile(plan, target, selection_context=context)
    assert (
        next(r for r in second["tickets"] if r["id"] == t.id)["state"]
        == "preserved_owned"
    )
    context["observation"]["quality_issues"].append(
        {
            "code": "TEST_NOTE",
            "severity": "info",
            "message": "New observation note",
            "affected_refs": [],
            "next_action": "Review",
        }
    )
    changed = compose_selection_plan(
        context["observation"], context["catalog"], context["adoptions"]
    )
    original = Store._update_ticket_unlocked
    seen = []

    def conflicted(self, id, **kwargs):
        seen.append(kwargs["expected_updated_at"])
        raise module.TicketUpdatedAtConflictError(
            "ticket_updated_at_precondition_failed"
        )

    monkeypatch.setattr(Store, "_update_ticket_unlocked", conflicted)
    result = feed_to_planfile(changed, target, selection_context=context)
    assert not result["ok"] and "precondition" in result["error"] and seen
    monkeypatch.setattr(Store, "_update_ticket_unlocked", original)


def test_selection_export_serializes_concurrent_retries(tmp_path):
    pytest.importorskip("planfile.core.store")
    from concurrent.futures import ThreadPoolExecutor

    _, target, plan, context = _selection_export_fixture(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: feed_to_planfile(plan, target, selection_context=context),
                range(2),
            )
        )
    assert all(r["ok"] for r in results), results
    assert sum(r["created"] for r in results) == len(plan["decisions"])


def test_selection_export_fails_before_writes_for_stale_or_unsupported_input(
    tmp_path, monkeypatch
):
    planfile = pytest.importorskip("planfile")
    source, target, plan, context = _selection_export_fixture(tmp_path)
    monkeypatch.setattr(planfile, "__version__", "unsupported")
    result = feed_to_planfile(plan, target, selection_context=context)
    assert not result["ok"] and "Unsupported" in result["error"]
    assert not (target / ".planfile").exists()
    (source / "demo.py").write_text("value=2\n")
    result = feed_to_planfile(plan, target, selection_context=context)
    assert not result["ok"] and "PLAN_STALE" in result["error"]
    assert not (target / ".planfile").exists()


def test_selection_export_refuses_storage_symlink_and_observed_source_target(tmp_path):
    pytest.importorskip("planfile.core.store")
    source, target, plan, context = _selection_export_fixture(tmp_path)
    result = feed_to_planfile(plan, source, selection_context=context)
    assert not result["ok"] and not (source / ".planfile").exists()
    outside = tmp_path / "outside"
    outside.mkdir()
    (target / ".planfile").symlink_to(outside, target_is_directory=True)
    result = feed_to_planfile(plan, target, selection_context=context)
    assert not result["ok"] and not list(outside.iterdir())


@pytest.mark.parametrize(
    "change",
    [
        {"executor": None},
        {"execution": None},
        {"source": None},
        {"status": "in_progress"},
        {"execution": {"assigned_to": "owner:reviewer"}},
        {"execution": {"started_at": "2026-10-08T00:00:00Z"}},
        {"execution": {"lease_expires_at": "2026-10-08T01:00:00Z"}},
        {"execution": {"finished_at": "2026-10-08T01:00:00Z"}},
        {"execution": {"queue": "another-controller"}},
        {"source": {"tool": "another-producer"}},
        {"source": {"version": "unknown"}},
        {"source": {"context": {"grants_authority": True}}},
        {"source": {"context": {}}},
    ],
)
def test_selection_export_preserves_missing_or_claimed_metadata(tmp_path, change):
    Store = pytest.importorskip("planfile.core.store").Store
    _, target, plan, context = _selection_export_fixture(tmp_path)
    first = feed_to_planfile(plan, target, selection_context=context)
    assert first["ok"]
    store = Store(target)
    ticket = store.get_ticket(first["tickets"][0]["id"])
    update = dict(change)
    for field in ("execution", "source"):
        if field in update and update[field] is not None:
            update[field] = {
                **getattr(ticket, field).model_dump(mode="json"),
                **update[field],
            }
    claimed = store.update_ticket(
        ticket.id, expected_updated_at=ticket.updated_at.isoformat(), **update
    )
    before = claimed.model_dump(mode="json")
    second = feed_to_planfile(plan, target, selection_context=context)
    assert second["ok"] and second["created"] == 0
    assert (
        next(r for r in second["tickets"] if r["id"] == ticket.id)["state"]
        == "preserved_owned"
    )
    assert store.get_ticket(ticket.id).model_dump(mode="json") == before
