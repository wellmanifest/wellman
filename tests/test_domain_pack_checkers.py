"""Unit tests for S1 domain pack checkers (nohardcode, semver, ssot)."""

from __future__ import annotations

import json
from pathlib import Path

from wellman.runner import ConformanceRunner

SHA40 = "a" * 40
SHA64 = "b" * 64


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_nohardcode_policy_valid_and_negative_cases(tmp_path: Path) -> None:
    valid_policy = {
        "schema": "wellmanifest.nohardcode/policy/v1",
        "version": "0.2.0-dev",
        "profile": "strict",
        "engine_bindings": {
            "llm": {"enabled": True, "provider": "subllm"},
            "env_dsl": {"enabled": True},
        },
        "rules": {
            "NOHARDCODE-001": {"enabled": True, "severity": "error"},
        },
        "waivers": [
            {"path": "config/legacy.json", "rule": "NOHARDCODE-001", "reason": "Pinned fixture compatibility"},
        ],
    }
    _write(tmp_path / "nohardcode-policy.json", valid_policy)
    assert ConformanceRunner(tmp_path).run_standard("wellmanifest/nohardcode") == []

    # Wildcard waiver path, unknown engine, and invalid provider must fail closed
    invalid_policy = {
        **valid_policy,
        "engine_bindings": {
            "llm": {"enabled": True, "provider": "openai-raw"},
            "magic_box": {"enabled": True},
        },
        "waivers": [
            {"path": "../escape/*.json", "rule": "NOHARDCODE-001", "reason": "bad"},
        ],
    }
    _write(tmp_path / "nohardcode-policy.json", invalid_policy)
    codes = {f.code for f in ConformanceRunner(tmp_path).run_standard("wellmanifest/nohardcode")}
    assert "GOV-NOHARDCODE-ENGINE-INVALID" in codes
    assert "GOV-NOHARDCODE-WAIVER-INVALID" in codes

    # Duplicate JSON keys fail closed
    (tmp_path / "nohardcode-policy.json").write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
    dup_codes = {f.code for f in ConformanceRunner(tmp_path).run_standard("wellmanifest/nohardcode")}
    assert "GOV-NOHARDCODE-POLICY-INVALID" in dup_codes


def test_semver_pack_valid_and_negative_cases(tmp_path: Path) -> None:
    # Missing carrier and manifests -> GOV-SEMVER-MISSING
    missing = ConformanceRunner(tmp_path).run_standard("wellmanifest/semver")
    assert [f.code for f in missing] == ["GOV-SEMVER-MISSING"]

    # Invalid VERSION string
    (tmp_path / "VERSION").write_text("v1.2\n", encoding="utf-8")
    bad_ver = ConformanceRunner(tmp_path).run_standard("wellmanifest/semver")
    assert any(f.code == "GOV-SEMVER-VERSION-INVALID" for f in bad_ver)

    # Valid VERSION + embedded-release + pipeline-run + hardware-matrix + policy
    (tmp_path / "VERSION").write_text("1.2.3\n", encoding="utf-8")
    _write(tmp_path / "policy.json", {
        "schema": "wellmanifest.semver/policy/v1",
        "authority": "none",
        "effect_model": "read-only-conformance",
        "rules": [{"id": "SEMVER-001", "topic": "separation"}],
    })
    _write(tmp_path / "examples" / "release.json", {
        "schema": "wellmanifest.semver/embedded-release/v1",
        "system_version": "1.2.3",
        "components": [
            {
                "component_id": "mcu-fw",
                "tier": "microcontroller_firmware",
                "target_hardware": "M5Stack CoreS3",
                "version": "1.14.0",
                "git_commit": SHA40,
                "binary_identity": {
                    "sha256": SHA64,
                    "elf_sha256": SHA64,
                    "target_partition": "ota_0",
                },
            }
        ],
        "compatibility": {"oql_contract_version": "v1"},
        "pipeline_attestation": {
            "dual_build_verified": True,
            "hil_simulation_passed": True,
            "safe_state_preconditions_verified": True,
        },
    })
    _write(tmp_path / "examples" / "pipeline.json", {
        "schema": "wellmanifest.semver/pipeline-run/v1",
        "commit_sha": SHA40,
        "verdict": "PASSED",
        "stages": {
            "dual_build": {"passed": True, "host_container_sha256": SHA64, "firmware_elf_sha256": SHA64},
            "safe_state_validation": {
                "passed": True, "motors_deenergized": True, "pumps_stopped": True, "valves_closed": True,
            },
        },
    })
    _write(tmp_path / "examples" / "matrix.json", {
        "schema": "wellmanifest.semver/hardware-matrix/v1",
        "matrix_version": "2026.10",
        "profiles": [{
            "profile_id": "cores3",
            "board_model": "M5Stack CoreS3",
            "soc": "ESP32-S3",
            "supported_firmware_semver_range": ">=1.0.0 <2.0.0",
        }],
    })
    assert ConformanceRunner(tmp_path).run_standard("wellmanifest/semver") == []

    # Single-bank OTA partition or unsafe pipeline preconditions must fail
    _write(tmp_path / "examples" / "release.json", {
        "schema": "wellmanifest.semver/embedded-release/v1",
        "system_version": "1.2.3",
        "components": [{
            "component_id": "mcu-fw",
            "tier": "microcontroller_firmware",
            "target_hardware": "M5Stack CoreS3",
            "version": "1.14.0",
            "git_commit": SHA40,
            "binary_identity": {"sha256": SHA64, "elf_sha256": SHA64, "target_partition": "factory_single"},
        }],
        "compatibility": {"oql_contract_version": "v1"},
        "pipeline_attestation": {
            "dual_build_verified": True,
            "hil_simulation_passed": True,
            "safe_state_preconditions_verified": False,
        },
    })
    neg_codes = {f.code for f in ConformanceRunner(tmp_path).run_standard("wellmanifest/semver")}
    assert "SEMVER-013" in neg_codes
    assert "SEMVER-012" in neg_codes


def test_ssot_pack_valid_and_negative_cases(tmp_path: Path) -> None:
    missing = ConformanceRunner(tmp_path).run_standard("wellmanifest/ssot")
    assert [f.code for f in missing] == ["GOV-SSOT-MISSING"]

    _write(tmp_path / "app.ssot.json", {
        "schema": "wellmanifest.ssot/decision/v1",
        "id": "app.ssot",
        "version": "0.2.0",
        "context": {
            "subject": "app.ssot",
            "languages": ["python"],
            "packaging": ["vendored-copy"],
            "analyzer": {"present": True, "kind": "redup", "treatAsDebtUntilInterview": False},
        },
        "policy": {
            "kind": "pin_policy",
            "edit": "upstream",
            "onChange": "bump_pin",
            "forbid": ["delete_generated_mirror"],
        },
        "decisions": [{
            "id": "app.shared",
            "kind": "vendored_copy",
            "trees": ["packages/shared", "vendor/shared"],
            "rationale": "Standalone boundary requires gated vendored copy.",
            "actions": [{"do": "vendor_and_gate_drift"}],
        }],
        "questions": [],
    })
    _write(tmp_path / "standards-lock.json", {
        "schema": "wellmanifest.standards-lock/v1",
        "version": "1.0.0",
        "entries": [{
            "standard": "wellmanifest.dsl",
            "revision": SHA40,
            "contracts": [{"ref": "schema://v1", "digest": f"sha256:{SHA64}"}],
        }],
        "updatePolicy": {"onNewCompatible": "create_pr", "onBreaking": "create_ticket", "merge": "trusted-validator"},
    })
    assert ConformanceRunner(tmp_path).run_standard("wellmanifest/ssot") == []

    # Direct destructive action or self-merge updatePolicy must fail closed
    _write(tmp_path / "app.ssot.json", {
        "schema": "wellmanifest.ssot/decision/v1",
        "id": "app.ssot",
        "version": "0.2.0",
        "context": {
            "subject": "app.ssot",
            "languages": ["python"],
            "packaging": ["vendored-copy"],
            "analyzer": {"present": True, "kind": "redup", "treatAsDebtUntilInterview": False},
        },
        "policy": {"kind": "pin_policy", "edit": "upstream", "onChange": "bump_pin", "forbid": []},
        "decisions": [{
            "id": "app.shared",
            "kind": "vendored_copy",
            "trees": ["packages/shared"],
            "rationale": "Bad destructive action.",
            "actions": [{"do": "delete_now"}],
        }],
        "questions": [],
    })
    _write(tmp_path / "standards-lock.json", {
        "schema": "wellmanifest.standards-lock/v1",
        "version": "1.0.0",
        "entries": [{"standard": "wellmanifest.dsl", "revision": "main", "contracts": []}],
        "updatePolicy": {"merge": "self-admin"},
    })
    neg_codes = {f.code for f in ConformanceRunner(tmp_path).run_standard("wellmanifest/ssot")}
    assert "SSOT-ACTION-001" in neg_codes
    assert "SSOT-PIN-001" in neg_codes
    assert "SSOT-POLICY-001" in neg_codes
