"""Tests for ConformanceRunner."""

from pathlib import Path
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


