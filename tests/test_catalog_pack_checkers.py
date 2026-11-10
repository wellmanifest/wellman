"""Unit tests for the S1 static conformance checkers of the remaining 14 catalog standards."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from wellman.runner import ConformanceRunner


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


@pytest.mark.parametrize(
    ("standard_id", "missing_code"),
    [
        ("wellmanifest/authority-lifecycle", "GOV-AUTHORITY-LIFECYCLE-MISSING"),
        ("wellmanifest/repair-lifecycle", "GOV-REPAIR-LIFECYCLE-MISSING"),
        ("wellmanifest/account-runtime", "GOV-ACCOUNT-RUNTIME-MISSING"),
        ("wellmanifest/skills", "GOV-SKILLS-MISSING"),
        ("wellmanifest/status", "GOV-STATUS-MISSING"),
        ("wellmanifest/performance", "GOV-PERFORMANCE-MISSING"),
        ("wellmanifest/llm", "GOV-LLM-MISSING"),
        ("wellmanifest/dsl", "GOV-DSL-MISSING"),
        ("wellmanifest/env-dsl", "GOV-ENV-DSL-MISSING"),
        ("wellmanifest/code-dsl", "GOV-CODE-DSL-MISSING"),
        ("wellmanifest/nl-dsl-llm", "GOV-NL-DSL-LLM-MISSING"),
        ("wellmanifest/nl-api-llm", "GOV-NL-API-LLM-MISSING"),
        ("wellmanifest/poa", "GOV-POA-MISSING"),
        ("wellmanifest/anonym", "GOV-ANONYM-MISSING"),
    ],
)
def test_selected_standard_fails_closed_when_artifact_missing(tmp_path: Path, standard_id: str, missing_code: str) -> None:
    findings = ConformanceRunner(tmp_path).run_standard(standard_id)
    assert [f.code for f in findings] == [missing_code]


def test_authority_and_repair_lifecycle_valid_and_invalid(tmp_path: Path) -> None:
    lease_path = tmp_path / ".subactor" / "leases" / "ticket-001--demo.json"
    _write_json(
        lease_path,
        {
            "schema": "wellmanifest.change-lease/v1",
            "leaseId": "allocation-ticket-001-demo",
            "ticketId": "ticket-001",
            "ownerActor": "agent:antigravity",
            "ownerSession": "session-1",
            "phase": "claimed",
            "leaseRevision": 1,
            "fencingToken": 1,
            "issuedAt": "2026-11-10T20:00:00Z",
            "expiresAt": "2026-11-10T22:00:00Z",
        },
    )
    assert ConformanceRunner(tmp_path).run_standard("wellmanifest/authority-lifecycle") == []

    _write_json(
        lease_path,
        {
            "schema": "wellmanifest.change-lease/v1",
            "leaseId": "allocation-ticket-001-demo",
            "ticketId": "ticket-001",
            "ownerActor": "agent:antigravity",
            "ownerSession": "session-1",
            "phase": "claimed",
            "leaseRevision": 0,
            "fencingToken": 1,
            "issuedAt": "2026-11-10T20:00:00",
            "expiresAt": "2026-11-10T22:00:00Z",
        },
    )
    codes = {f.code for f in ConformanceRunner(tmp_path).run_standard("wellmanifest/authority-lifecycle")}
    assert "GOV-AUTHORITY-LIFECYCLE-FENCING" in codes
    assert "GOV-AUTHORITY-LIFECYCLE-EXPIRY" in codes

    repair_path = tmp_path / ".governance" / "repair-lifecycle.json"
    _write_json(
        repair_path,
        {
            "schema": "wellmanifest.repair-lifecycle/case/v1",
            "problem": {
                "diagnosticId": "repair://diagnostic/disk-full",
                "observationOnly": True,
            },
        },
    )
    assert ConformanceRunner(tmp_path).run_standard("wellmanifest/repair-lifecycle") == []

    _write_json(
        repair_path,
        {
            "schema": "wellmanifest.repair-lifecycle/case/v1",
            "problem": {
                "diagnosticId": "repair://diagnostic/disk-full",
                "observationOnly": False,
            },
        },
    )
    assert [f.code for f in ConformanceRunner(tmp_path).run_standard("wellmanifest/repair-lifecycle")] == [
        "GOV-REPAIR-LIFECYCLE-OBSERVATION"
    ]


def test_account_runtime_skills_status_and_performance(tmp_path: Path) -> None:
    acct_path = tmp_path / ".governance" / "account-runtime.json"
    _write_json(
        acct_path,
        {
            "schema": "wellmanifest.account-runtime/v1",
            "accounts": [{"id": "acct-1", "credentialRef": "vault://prod/github"}],
        },
    )
    assert ConformanceRunner(tmp_path).run_standard("wellmanifest/account-runtime") == []

    _write_json(
        acct_path,
        {
            "schema": "wellmanifest.account-runtime/v1",
            "accounts": [{"id": "acct-1", "token": "ghp_1234567890abcdefghijklmnopqrstuv"}],
        },
    )
    assert "GOV-ACCOUNT-RUNTIME-SECRET" in {
        f.code for f in ConformanceRunner(tmp_path).run_standard("wellmanifest/account-runtime")
    }

    skill_md = tmp_path / "skills" / "demo" / "SKILL.md"
    skill_md.parent.mkdir(parents=True, exist_ok=True)
    skill_md.write_text("---\nname: demo-skill\ndescription: Safe skill contract\n---\n# Demo\n", encoding="utf-8")
    assert ConformanceRunner(tmp_path).run_standard("wellmanifest/skills") == []

    skill_md.write_text("# Missing frontmatter\n", encoding="utf-8")
    assert [f.code for f in ConformanceRunner(tmp_path).run_standard("wellmanifest/skills")] == ["GOV-SKILLS-FRONTMATTER"]

    status_path = tmp_path / "contracts" / "status.contract.json"
    _write_json(
        status_path,
        {
            "schema": "wellmanifest.status/contract-bundle/v1",
            "modelAuthority": "propose-only",
            "profiles": {
                "cycle/v1": {
                    "initial": "queued",
                    "states": ["queued", "done"],
                    "terminal": ["done"],
                    "transitions": {"queued": ["done"], "done": []},
                }
            },
        },
    )
    assert ConformanceRunner(tmp_path).run_standard("wellmanifest/status") == []

    _write_json(
        status_path,
        {
            "schema": "wellmanifest.status/contract-bundle/v1",
            "modelAuthority": "commit-direct",
            "profiles": {
                "cycle/v1": {
                    "initial": "queued",
                    "states": ["queued", "done"],
                    "terminal": ["done"],
                    "transitions": {"queued": ["done"], "done": ["queued"]},
                }
            },
        },
    )
    status_codes = {f.code for f in ConformanceRunner(tmp_path).run_standard("wellmanifest/status")}
    assert {"GOV-STATUS-AUTHORITY", "GOV-STATUS-GRAPH"}.issubset(status_codes)

    perf_path = tmp_path / ".governance" / "performance-budget.json"
    _write_json(
        perf_path,
        {
            "schema": "wellmanifest.performance-budget/v1",
            "budgets": [{"name": "p95-dispatch", "maxLatencyMs": 150}],
        },
    )
    assert ConformanceRunner(tmp_path).run_standard("wellmanifest/performance") == []

    _write_json(
        perf_path,
        {
            "schema": "wellmanifest.performance-budget/v1",
            "budgets": [{"name": "p95-dispatch", "maxLatencyMs": 0}],
        },
    )
    assert [f.code for f in ConformanceRunner(tmp_path).run_standard("wellmanifest/performance")] == [
        "GOV-PERFORMANCE-BUDGET"
    ]


def test_llm_dsl_poa_anonym_and_symlink_refusal(tmp_path: Path) -> None:
    _write_json(
        tmp_path / ".wellmanifest" / "llm.json",
        {
            "schema": "wellmanifest.llm-profile/v1",
            "profileId": "subactor-first",
            "version": "1.0.0",
            "transport": {"preferred": "mcp"},
            "workflow": [{"id": "discover", "operation": "profile.resolve"}],
        },
    )
    assert ConformanceRunner(tmp_path).run_standard("wellmanifest/llm") == []

    _write_json(
        tmp_path / "dsl-manifest.json",
        {
            "schema": "wellmanifest.dsl/manifest/v1",
            "id": "wellmanifest.demo-dsl",
            "name": "Demo DSL",
            "version": "0.1.0",
            "domain": "governance",
        },
    )
    assert ConformanceRunner(tmp_path).run_standard("wellmanifest/dsl") == []

    _write_json(
        tmp_path / "env-dsl.json",
        {
            "schema": "wellmanifest.env-dsl/v1",
            "variables": {
                "SERVICE_PORT": {"secret": False, "default": "8080"},
                "API_TOKEN": {"secret": True},
            },
        },
    )
    assert ConformanceRunner(tmp_path).run_standard("wellmanifest/env-dsl") == []

    _write_json(
        tmp_path / "code-dsl.json",
        {
            "schema": "wellmanifest.code/json/v1",
            "documents": [{"kind": "query", "uri": "repo://wellmanifest/wellman/src/wellman/runner.py"}],
        },
    )
    assert ConformanceRunner(tmp_path).run_standard("wellmanifest/code-dsl") == []

    _write_json(
        tmp_path / "code-dsl.json",
        {
            "schema": "wellmanifest.code/json/v1",
            "documents": [{"kind": "query", "uri": "file:///etc/passwd"}],
        },
    )
    assert [f.code for f in ConformanceRunner(tmp_path).run_standard("wellmanifest/code-dsl")] == ["GOV-CODE-DSL-FILE-URI"]

    _write_json(
        tmp_path / ".governance" / "nl-dsl-llm.json",
        {
            "schema": "wellmanifest.nl-dsl-llm/v1",
            "nl": {"grammar": "pl-en"},
            "dsl": {"id": "wellmanifest.demo-dsl"},
            "llm": {"profileId": "subactor-first"},
            "transports": ["mcp", "cli"],
        },
    )
    assert ConformanceRunner(tmp_path).run_standard("wellmanifest/nl-dsl-llm") == []

    _write_json(
        tmp_path / "api-registry.json",
        {
            "schema": "wellmanifest.api-registry/v1",
            "version": "1.0.0",
            "services": [{"id": "core", "name": "Core Service", "protocol": "mcp"}],
            "endpoints": [{"id": "health", "serviceId": "core"}],
        },
    )
    assert ConformanceRunner(tmp_path).run_standard("wellmanifest/nl-api-llm") == []

    poa_path = tmp_path / "poa-process.json"
    _write_json(
        poa_path,
        {
            "schema": "poa.process/v1",
            "process_id": "deploy-verify",
            "steps": [
                {"id": "step-1", "action": "inspect", "depends_on": []},
                {"id": "step-2", "action": "verify", "depends_on": ["step-1"]},
            ],
        },
    )
    assert ConformanceRunner(tmp_path).run_standard("wellmanifest/poa") == []

    _write_json(
        poa_path,
        {
            "schema": "poa.process/v1",
            "process_id": "deploy-verify",
            "steps": [
                {"id": "step-1", "action": "inspect", "depends_on": ["step-2"]},
                {"id": "step-2", "action": "verify", "depends_on": ["step-1"]},
            ],
        },
    )
    assert [f.code for f in ConformanceRunner(tmp_path).run_standard("wellmanifest/poa")] == ["GOV-POA-DAG"]

    payload = "Hello PERSON-1 at EMAIL-1"
    anonym_path = tmp_path / ".governance" / "anonym.json"
    _write_json(
        anonym_path,
        {
            "schema": "wellmanifest.anonym/v1",
            "policy": "context-preserving-v1",
            "mappingId": "map-001",
            "payload": payload,
            "payloadSha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            "aliasCounts": {"PERSON": 1, "EMAIL": 1},
        },
    )
    assert ConformanceRunner(tmp_path).run_standard("wellmanifest/anonym") == []

    # Symlink refusal check
    outside = tmp_path.parent / "outside_anonym.json"
    outside.write_text(anonym_path.read_text(encoding="utf-8"), encoding="utf-8")
    anonym_path.unlink()
    anonym_path.symlink_to(outside)
    assert [f.code for f in ConformanceRunner(tmp_path).run_standard("wellmanifest/anonym")] == ["GOV-ANONYM-INVALID"]
