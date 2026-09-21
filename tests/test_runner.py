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
