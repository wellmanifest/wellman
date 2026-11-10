"""Unit tests for S1 URI and task domain pack checkers (uriprocess, taskand, nl-uri-dsl-llm)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from wellman.runner import ConformanceRunner


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def test_uriprocess_pack_valid_and_negative_cases(tmp_path: Path) -> None:
    version_file = tmp_path / "VERSION"
    version_file.write_text("0.3.0\n", encoding="utf-8")
    policy_file = tmp_path / "policy.json"
    _write_json(policy_file, {
        "schema": "wellmanifest.uriprocess/policy/v1",
        "standard": "wellmanifest/uriprocess",
        "version": "0.3.0",
        "execution_authority": False,
    })
    _write_json(tmp_path / "bundle.json", {
        "schema": "wellmanifest.uriprocess/bundle/v1",
        "standard": "wellmanifest/uriprocess",
        "version": "0.3.0",
        "files": {
            "VERSION": hashlib.sha256(version_file.read_bytes()).hexdigest(),
            "policy.json": hashlib.sha256(policy_file.read_bytes()).hexdigest(),
        },
    })
    _write_json(tmp_path / "uriprocess.json", {
        "schema": "uriprocess.rust-package/v1",
        "public_uris": ["proc://demo/worker/run"],
        "crate": "demo_worker",
        "transports": ["cdylib", "json-stdin-stdout"],
        "fallback_chain": ["floor:python_stdlib", "standard:cdylib"],
    })
    _write_json(tmp_path / "provenance.json", {
        "upstream_commit": "a" * 40,
        "tests": ["tests/test_worker.py"],
    })

    runner = ConformanceRunner(tmp_path)
    assert runner.run_standard("wellmanifest/uriprocess") == []

    # Corrupt bundle hash, provenance, and rust-uri-v1 requirements
    version_file.write_text("0.3.1\n", encoding="utf-8")
    _write_json(tmp_path / "uriprocess.json", {
        "schema": "uriprocess.rust-package/v1",
        "public_uris": ["proc://demo/worker/run", "proc://demo/worker/run"],
        "crate": "",
        "transports": ["unsupported"],
        "fallback_chain": [],
    })
    _write_json(tmp_path / "provenance.json", {
        "upstream_commit": "not-a-sha",
        "tests": ["../escape.py"],
    })
    codes = {f.code for f in runner.run_standard("wellmanifest/uriprocess")}
    assert "URP-INTEGRITY-MISMATCH" in codes
    assert "URP-IDENTITY-001" in codes
    assert "URP-SCHEMA-001" in codes
    assert "URP-TESTS-001" in codes


def test_taskand_pack_valid_and_dag_or_grant_violations(tmp_path: Path) -> None:
    runner = ConformanceRunner(tmp_path)
    assert [f.code for f in runner.run_standard("wellmanifest/taskand")] == ["GOV-TASKAND-MISSING"]

    _write_json(tmp_path / "capsule.json", {
        "schema": "taskand.capsule/v1",
        "id": "demo-capsule",
        "grants": [{"capability": "fs.read", "scope": "docs/"}],
        "tasks": [
            {"id": "prepare", "depends_on": []},
            {"id": "verify", "depends_on": ["prepare"]},
        ],
    })
    assert runner.run_standard("wellmanifest/taskand") == []

    # Wildcard grant + cyclic DAG + duplicate JSON key
    _write_json(tmp_path / "capsule.json", {
        "schema": "taskand.capsule/v1",
        "id": "",
        "grants": [{"capability": "*", "scope": "*"}],
        "tasks": [
            {"id": "step-a", "depends_on": ["step-b"]},
            {"id": "step-b", "depends_on": ["step-a"]},
        ],
    })
    (tmp_path / "grants.json").write_text('{"grants": [], "grants": []}', encoding="utf-8")
    codes = {f.code for f in runner.run_standard("wellmanifest/taskand")}
    assert "GOV-TASKAND-CAPSULE-ID" in codes
    assert "GOV-TASKAND-WILDCARD-GRANT" in codes
    assert "GOV-TASKAND-DAG-CYCLE" in codes
    assert "GOV-TASKAND-DOC-INVALID" in codes


def test_nl_uri_dsl_llm_pack_valid_and_negative_cases(tmp_path: Path) -> None:
    runner = ConformanceRunner(tmp_path)
    assert [f.code for f in runner.run_standard("wellmanifest/nl-uri-dsl-llm")] == ["GOV-NL-URI-MISSING"]

    _write_json(tmp_path / "profiles" / "semantic-v1.json", {
        "profile": "semantic-v1",
        "envelope": "wellmanifest.nl-plan/v1",
        "lexical_admission": False,
        "compilation_executes": False,
        "exchange": {
            "profile": "uri-urn-exchange-v1",
            "envelope": "wellmanifest.process-exchange/v1",
            "authority_from_envelope": False,
        },
    })
    _write_json(tmp_path / "conformance" / "nl-uri-plan.json", {
        "schema": "wellmanifest.nl-plan/v1",
        "status": "ok",
        "operation": "proc://willmux/voice/resolve/v1",
    })
    _write_json(tmp_path / "conformance" / "process-exchange.json", {
        "schema": "wellmanifest.process-exchange/v1",
        "kind": "request",
        "messageUrn": "urn:uuid:11111111-2222-4333-8444-555555555555",
        "requestUrn": "urn:uuid:66666666-7777-4888-9999-aaaaaaaaaaaa",
        "operation": "proc://willmux/run/instruction/v1",
        "contractDigest": "b" * 64,
        "effects": ["read", "execute"],
    })
    _write_json(tmp_path / "conformance" / "snapshot.json", {
        "schema": "wellmanifest.conversational-process-snapshot/v1",
        "state": {"focus": "A"},
        "chat": {"messageCount": 0, "messages": []},
        "processes": {
            "activeProcessId": None,
            "items": [{
                "id": "1",
                "urn": "urn:dockuri:proc:abc123",
                "uri": "process://host/dockuri?proc=demo",
                "command": "demo",
                "status": "completed",
            }],
        },
    })
    assert runner.run_standard("wellmanifest/nl-uri-dsl-llm") == []

    # Break safety invariants and envelope contracts
    _write_json(tmp_path / "profiles" / "semantic-v1.json", {
        "profile": "semantic-v1",
        "envelope": "wrong",
        "lexical_admission": True,
        "compilation_executes": True,
        "exchange": {"authority_from_envelope": True},
    })
    _write_json(tmp_path / "conformance" / "nl-uri-plan.json", {
        "schema": "wellmanifest.nl-plan/v1",
        "status": "ok",
        "operation": "not a uri",
    })
    _write_json(tmp_path / "conformance" / "process-exchange.json", {
        "schema": "wellmanifest.process-exchange/v1",
        "kind": "invalid",
        "messageUrn": "bad",
        "requestUrn": "bad",
        "operation": "bad",
        "contractDigest": "123",
        "effects": ["root"],
    })
    _write_json(tmp_path / "conformance" / "snapshot.json", {
        "schema": "wellmanifest.conversational-process-snapshot/v1",
        "state": {},
        "chat": {},
        "processes": {"items": [{"urn": "bad", "uri": "http://bad"}]},
    })
    codes = {f.code for f in runner.run_standard("wellmanifest/nl-uri-dsl-llm")}
    assert "GOV-NL-URI-PROFILE-ENVELOPE" in codes
    assert "GOV-NL-URI-PROFILE-SAFETY" in codes
    assert "GOV-NL-URI-EXCHANGE-AUTHORITY" in codes
    assert "GOV-NL-URI-PLAN-URI" in codes
    assert "GOV-NL-URI-EXCHANGE-KIND" in codes
    assert "GOV-NL-URI-EXCHANGE-URN" in codes
    assert "GOV-NL-URI-EXCHANGE-DIGEST" in codes
    assert "GOV-NL-URI-EXCHANGE-EFFECTS" in codes
    assert "GOV-NL-URI-SNAPSHOT-URI" in codes
