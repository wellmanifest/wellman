"""Unit tests for wellmanifest/flowguard conformance gate in wellman."""

from pathlib import Path
import pytest

from wellman.registry import STANDARDS_CATALOG, get_standard
from wellman.runner import ConformanceRunner


def test_flowguard_standard_registration():
    standard = get_standard("wellmanifest/flowguard")
    assert standard is not None
    assert standard.id == "wellmanifest/flowguard"
    assert standard.owner == "wellmanifest/flowguard"
    assert standard.minimum_level == "S3"

    alias_standard = get_standard("flowguard")
    assert alias_standard is not None
    assert alias_standard.id == "wellmanifest/flowguard"


def test_check_flowguard_missing(tmp_path: Path):
    runner = ConformanceRunner(tmp_path)
    findings = runner.check_flowguard()
    assert len(findings) == 1
    assert findings[0].code == "GOV-FLOWGUARD-MISSING"


def test_check_flowguard_satisfied_via_policy(tmp_path: Path):
    policy_file = tmp_path / "flowguard.policy.json"
    policy_file.write_text('{"schema": "wellmanifest.flowguard/policy/v1"}', encoding="utf-8")

    runner = ConformanceRunner(tmp_path)
    findings = runner.check_flowguard()
    assert not any(f.code == "GOV-FLOWGUARD-MISSING" for f in findings)


def test_check_flowguard_unbounded_subprocess(tmp_path: Path):
    (tmp_path / "flowguard").mkdir()
    bad_code = tmp_path / "flowguard" / "task.py"
    bad_code.write_text(
        "import subprocess\n"
        "# flowguard task runner\n"
        "def run_step():\n"
        "    subprocess.run(['long_running_job'])\n",
        encoding="utf-8",
    )

    runner = ConformanceRunner(tmp_path)
    findings = runner.check_flowguard()
    assert any(f.code == "GOV-FLOWGUARD-UNBOUNDED-EXECUTION" for f in findings)


def test_flowguard_applicability_rule():
    from wellman.applicability import RULES
    assert "wellmanifest/flowguard" in RULES
    rule = RULES["wellmanifest/flowguard"]
    assert rule["scope"] == "component"
    assert rule["applies_when"]["all"][0]["feature"] == "runtime:flow-guard"

