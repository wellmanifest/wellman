"""Tests for standard dependency DAGs, SSoT catalog parity, and dockuri parity checks."""

from __future__ import annotations

import json
from pathlib import Path

from wellman.registry import (
    PROFILES_CATALOG,
    STANDARDS_CATALOG,
    expand_standard_dependencies,
    get_standard,
    missing_standard_dependencies,
)
from wellman.runner import ConformanceRunner
from wellman.validator import StandardsValidator, get_schemas_dir


def test_all_catalog_dependencies_exist_and_are_acyclic():
    resolved = expand_standard_dependencies(STANDARDS_CATALOG.keys())
    assert set(resolved.keys()) == set(STANDARDS_CATALOG.keys())
    for pack in STANDARDS_CATALOG.values():
        for dep in pack.requires:
            assert dep in STANDARDS_CATALOG, f"{pack.id} requires unknown {dep}"


def test_standard_packs_json_matches_registry_ssot():
    sp_path = get_schemas_dir() / "standard-packs.json"
    data = json.loads(sp_path.read_text(encoding="utf-8"))
    pack_ids = {p["id"] for p in data["packs"]}
    assert pack_ids == set(STANDARDS_CATALOG.keys())
    expected_profiles = {k for k in PROFILES_CATALOG if k != "full"}
    assert set(data["profiles"].keys()) == expected_profiles


def test_missing_standard_dependencies_detects_missing_base_standards():
    # dockuri requires uriprocess and mcp
    missing = missing_standard_dependencies(["wellmanifest/dockuri"])
    assert missing == {"wellmanifest/dockuri": ["wellmanifest/mcp", "wellmanifest/uriprocess"]}

    # nl-dsl-llm requires dsl and llm
    missing_nl = missing_standard_dependencies(["wellmanifest/nl-dsl-llm", "wellmanifest/dsl"])
    assert missing_nl == {"wellmanifest/nl-dsl-llm": ["wellmanifest/llm"]}


def test_validator_detects_incomplete_profile_and_missing_dependencies(tmp_path: Path):
    gov = tmp_path / ".governance"
    gov.mkdir()
    (gov / "standard-requirements.json").write_text(
        json.dumps(
            {
                "schema": "wellman.standard-requirements/v1",
                "profiles": ["baseline"],
                "requirements": [
                    {"id": "wellmanifest/new-project", "minimumLevel": "S4"},
                    {"id": "wellmanifest/dockuri", "minimumLevel": "S3"},
                ],
            }
        ),
        encoding="utf-8",
    )
    findings = StandardsValidator(tmp_path).validate_standard_dependencies()
    codes = {f.code for f in findings}
    assert "STD-PROFILE-REQ-MISSING" in codes
    assert "STD-DEP-MISSING" in codes


def test_check_dockuri_detects_manifest_uri_drift_and_passes_when_synced(tmp_path: Path):
    (tmp_path / "dockuri.json").write_text(
        json.dumps(
            {
                "project": {"name": "demo", "version": "0.4.5"},
                "processes": [
                    {"uri": "proc://demo/a/v1"},
                    {"uri": "proc://demo/b/v1"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "uriprocess.json").write_text(
        json.dumps(
            {
                "name": "demo",
                "version": "0.4.4",
                "public_uris": ["proc://demo/a/v1"],
            }
        ),
        encoding="utf-8",
    )
    runner = ConformanceRunner(tmp_path)
    findings = runner.check_dockuri()
    codes = {f.code for f in findings}
    assert "GOV-DOCKURI-URIPROCESS-DRIFT" in codes
    assert "GOV-DOCKURI-VERSION-DRIFT" in codes

    # Fix uriprocess.json to match dockuri.json
    (tmp_path / "uriprocess.json").write_text(
        json.dumps(
            {
                "name": "demo",
                "version": "0.4.5",
                "public_uris": ["proc://demo/a/v1", "proc://demo/b/v1"],
            }
        ),
        encoding="utf-8",
    )
    assert runner.check_dockuri() == []


def test_check_mcp_and_dockuri_procedures_work_in_worktree_path(tmp_path: Path):
    wt = tmp_path / ".worktrees" / "ticket-001--demo"
    (wt / "src" / "demo").mkdir(parents=True)
    (wt / "src" / "demo" / "mcp_server.py").write_text("# mcp server\n", encoding="utf-8")
    (wt / "dockuri.json").write_text(
        json.dumps(
            {
                "app": "demo",
                "version": "0.4.5",
                "procedures": {
                    "ping": {"uri": "proc://demo/ping/v1"},
                },
            }
        ),
        encoding="utf-8",
    )
    (wt / "uriprocess.json").write_text(
        json.dumps(
            {
                "package": "demo",
                "version": "0.4.5",
                "public_uris": ["proc://demo/ping/v1"],
            }
        ),
        encoding="utf-8",
    )
    runner = ConformanceRunner(wt)
    assert runner.check_mcp() == []
    assert runner.check_dockuri() == []
