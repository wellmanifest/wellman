"""Tests for ConformanceRunner."""

from pathlib import Path
import subprocess

import pytest

from wellman.runner import ConformanceRunner


def test_runner_on_empty_dir(tmp_path):
    runner = ConformanceRunner(tmp_path)
    findings = runner.run_all()
    assert isinstance(findings, list)
    # On an empty directory, AGENTS.md missing should be warned
    warn_codes = [f.code for f in findings if f.severity == "WARNING"]
    assert "GOV-AGENT-001" in warn_codes


def test_runner_with_agents_md(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    runner = ConformanceRunner(tmp_path)
    agent_findings = runner.check_agent_hosts()
    assert len(agent_findings) == 0


def test_runner_selected_standard_uses_only_its_check(tmp_path):
    runner = ConformanceRunner(tmp_path)

    findings = runner.run_standard("wellmanifest/agent")

    assert [finding.code for finding in findings] == ["GOV-AGENT-001"]


def test_runner_selected_docs_requires_adoption(tmp_path):
    runner = ConformanceRunner(tmp_path)

    findings = runner.run_standard("wellmanifest/docs")

    assert [finding.code for finding in findings] == ["GOV-DOCS-MISSING"]


def test_runner_git_lifecycle_accepts_plf_ticket_branch(tmp_path, monkeypatch):
    import subprocess
    runner = ConformanceRunner(tmp_path)

    class DummyResult:
        stdout = "ticket/PLF-013-feature-description\n"

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: DummyResult())
    findings = runner.check_git_lifecycle()
    assert not any(f.code == "GOV-GIT-001" for f in findings)


def test_runner_selected_reuse_on_empty_dir(tmp_path):
    runner = ConformanceRunner(tmp_path)
    findings = runner.run_standard("wellmanifest/reuse")
    codes = [f.code for f in findings]
    assert "GOV-REUSE-NO-RECEIPT" in codes
    assert "GOV-REUSE-NO-PLANFILE" in codes
    assert "GOV-REUSE-NO-DOCS" in codes


def test_runner_selected_reuse_with_valid_setup(tmp_path):
    import json
    # 1. Setup receipt
    reuse_dir = tmp_path / ".reuse"
    reuse_dir.mkdir(parents=True)
    receipt_data = {
        "schema": "wellmanifest.reuse-scan-receipt/v1",
        "tool": {"name": "redup", "version": "0.4.48"},
        "revision": "a" * 40,
        "scanned": [{"path": "src/app.py", "sha256": "b" * 64}],
        "findings": {"clone_groups": 0, "unmitigated": 0},
    }
    (reuse_dir / "redup-receipt.json").write_text(json.dumps(receipt_data), encoding="utf-8")

    # 2. Setup planfile
    sprints_dir = tmp_path / ".planfile" / "sprints"
    sprints_dir.mkdir(parents=True)
    (sprints_dir / "current.yaml").write_text("sprint:\n  id: sprint-1\n  tickets: {}\n", encoding="utf-8")

    # 3. Setup docs
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "README.md").write_text("# Docs\n", encoding="utf-8")

    runner = ConformanceRunner(tmp_path)
    findings = runner.run_standard("wellmanifest/reuse")
    assert len(findings) == 0


def test_runner_selected_reuse_unmitigated_clones(tmp_path):
    import json
    reuse_dir = tmp_path / ".reuse"
    reuse_dir.mkdir(parents=True)
    receipt_data = {
        "schema": "wellmanifest.reuse-scan-receipt/v1",
        "tool": {"name": "redup", "version": "0.4.48"},
        "revision": "a" * 40,
        "scanned": [{"path": "src/app.py", "sha256": "b" * 64}],
        "findings": {"clone_groups": 2, "unmitigated": 2},
    }
    (reuse_dir / "redup-receipt.json").write_text(json.dumps(receipt_data), encoding="utf-8")

    # Setup docs and planfile
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "README.md").write_text("# Docs\n", encoding="utf-8")
    sprints_dir = tmp_path / ".planfile" / "sprints"
    sprints_dir.mkdir(parents=True)
    (sprints_dir / "current.yaml").write_text("sprint:\n  id: sprint-1\n  tickets: {}\n", encoding="utf-8")

    runner = ConformanceRunner(tmp_path)
    findings = runner.run_standard("wellmanifest/reuse")
    assert any(f.code == "GOV-REUSE-UNMITIGATED-CLONES" and f.severity == "ERROR" for f in findings)


@pytest.mark.parametrize("error", [PermissionError("denied"), subprocess.TimeoutExpired("checker", 15)])
def test_worktree_checker_execution_failure_is_an_error(tmp_path, monkeypatch, error):
    monkeypatch.setattr("wellman.runner._worktree_admission", lambda _: None)
    (tmp_path / ".git").mkdir()
    def execute(argv, **kwargs):
        if argv[0] == "git":
            return subprocess.CompletedProcess(argv, 0, str(tmp_path) + "\n", "")
        raise error

    monkeypatch.setattr(subprocess, "run", execute)
    findings = ConformanceRunner(tmp_path).check_worktrees()
    assert any(f.code == "GOV-WORKTREE-CHECK-002" and f.severity == "ERROR" for f in findings)


@pytest.mark.parametrize("stdout,stderr", [("", ""), ("", "cannot inspect checkout"), ("GOV-WORKTREE-OVERLAP ERROR conflict", "")])
def test_worktree_checker_nonzero_exit_always_fails(tmp_path, monkeypatch, stdout, stderr):
    monkeypatch.setattr("wellman.runner._worktree_admission", lambda _: None)
    (tmp_path / ".git").mkdir()

    def execute(argv, **kwargs):
        if argv[0] == "git":
            return subprocess.CompletedProcess(argv, 0, str(tmp_path) + "\n", "")
        return subprocess.CompletedProcess(argv, 2, stdout, stderr)

    monkeypatch.setattr(subprocess, "run", execute)
    findings = ConformanceRunner(tmp_path).check_worktrees()
    assert any(f.code == "GOV-WORKTREE-OVERLAP-001" and f.severity == "ERROR" for f in findings)


def test_worktree_checker_missing_cannot_pass(tmp_path, monkeypatch):
    monkeypatch.setattr("wellman.runner._worktree_admission", lambda _: None)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr("wellman.runner._find_bundled_script", lambda _: None)
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 0, str(tmp_path) + "\n", ""))
    assert any(f.code == "GOV-WORKTREE-CHECK-001" for f in ConformanceRunner(tmp_path).check_worktrees())


def test_worktree_conformance_requires_a_git_checkout(tmp_path):
    findings = ConformanceRunner(tmp_path).check_worktrees()
    assert any(f.severity == "ERROR" for f in findings)


def test_direct_gate_rejects_symlink_before_execution(tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: calls.append(args))
    assert ConformanceRunner(link).run_canonical_gate() == 1
    assert calls == []


def test_worktree_checker_real_subprocess_contract():
    import tempfile
    import shutil

    cache = Path.cwd() / ".subactor/cache/worktree-checker-tests"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as temporary:
        primary = Path(temporary)
        subprocess.run(["git", "-C", str(primary), "init", "-q"], check=True)
        source = Path(__file__).resolve().parents[1]
        paths = subprocess.check_output(["git", "-C", str(source), "ls-files", ".governance"], text=True).splitlines()
        for relative in paths:
            destination = primary / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, destination)
        subprocess.run(["git", "-C", str(primary), "add", ".governance"], check=True)
        subprocess.run(["git", "-C", str(primary), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "commit", "--allow-empty", "-qm", "fixture"], check=True)
        assert ConformanceRunner(primary).check_worktrees() == []


@pytest.mark.parametrize("payload", ["", "{}", '{"status":"passed"}', '{"schema":"new-project.worktree-overlap-report/v1","status":"passed","findings":[],"summary":{"errors":0,"warnings":0,"findings":0,"checkouts":0}}'])
def test_exit_zero_without_complete_observation_cannot_pass(tmp_path, monkeypatch, payload):
    monkeypatch.setattr("wellman.runner._worktree_admission", lambda _: None)
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 0, payload, ""))
    assert any(f.code == "GOV-WORKTREE-CHECK-004" for f in ConformanceRunner(tmp_path).check_worktrees())


def test_canonical_gate_uses_verified_adoption_and_rejects_drift(tmp_path, monkeypatch):
    import hashlib
    import json

    monkeypatch.setattr("wellman.runner._worktree_admission", lambda _: None)
    gov = tmp_path / ".governance"
    gov.mkdir()
    checker = gov / "governance_check.py"
    checker.write_text("# pinned fixture\n")
    (gov / "manifest.lock.json").write_text(json.dumps({"managedFiles": {
        ".governance/governance_check.py": hashlib.sha256(checker.read_bytes()).hexdigest()}}))
    called = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: called.append(cmd) or subprocess.CompletedProcess(cmd, 0))
    assert ConformanceRunner(tmp_path).run_canonical_gate(["--preflight"]) == 0
    assert called[0][1] == str(checker)
    checker.write_text("# changed bytes\n")
    called.clear()
    assert ConformanceRunner(tmp_path).run_canonical_gate() == 1
    assert called == []


def test_missing_adopted_checker_cannot_fall_back_to_bundled(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr("wellman.runner._worktree_admission", lambda _: None)
    gov = tmp_path / ".governance"
    gov.mkdir()
    (gov / "manifest.lock.json").write_text(json.dumps({"managedFiles": {
        ".governance/governance_check.py": "a" * 64}}))
    monkeypatch.setattr("wellman.runner._find_bundled_script", lambda _: pytest.fail("must not fall back"))
    assert ConformanceRunner(tmp_path).run_canonical_gate() == 1


