"""Tests for deterministic static conformance-pack checkers (ticket-095)."""

from __future__ import annotations

import json
from pathlib import Path

from wellman.runner import ConformanceRunner


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _valid_nolimits_bindings() -> dict:
    tools = {
        "LIM-STORAGE-001": ("semcod/fixos", "fixos cleanup --safe"),
        "LIM-TEST-002": ("semcod/testless", "testless prune"),
        "LIM-MERGE-003": ("subactor/validator-agent", "run-local-direct-pr.sh --merge"),
        "LIM-WORKTREE-004": ("wellmanifest/worktrees", "new-ticket.sh"),
        "LIM-DEPENDENCY-005": ("wellmanifest/python", "uv sync --locked"),
        "LIM-RESOURCE-006": ("wellmanifest/hostguard", "hostguard probe"),
        "LIM-CONTEXT-007": ("wellmanifest/session-recovery", "uncrash compact"),
        "LIM-FLAKY-008": ("semcod/testless", "testless quarantine"),
        "LIM-GOVERNANCE-009": ("wellmanifest/new-project", "governance-check.sh"),
        "LIM-COST-010": ("wellmanifest/llm", "subllm budget-check"),
    }
    return {
        "bindings": [
            {
                "code": code,
                "name": code.lower(),
                "dimension": "host",
                "remediationTool": tool,
                "command": cmd,
                "deterministic": True,
                "evidenceRequired": "receipt",
            }
            for code, (tool, cmd) in tools.items()
        ]
    }


def test_nolimits_checker_positive_and_negative(tmp_path: Path) -> None:
    runner = ConformanceRunner(tmp_path)
    assert [f.code for f in runner.run_standard("wellmanifest/nolimits")] == ["GOV-NOLIMITS-MISSING"]

    cfg = tmp_path / ".governance" / "nolimits.json"
    _write_json(cfg, _valid_nolimits_bindings())
    assert runner.run_standard("wellmanifest/nolimits") == []

    # Missing canonical codes + admin bypass + wrong tool
    bad = _valid_nolimits_bindings()
    bad["bindings"] = bad["bindings"][:3]
    bad["bindings"][0]["remediationTool"] = "rm-rf"
    bad["bindings"][2]["command"] = "gh pr merge --admin"
    _write_json(cfg, bad)
    codes = {f.code for f in runner.run_standard("wellmanifest/nolimits")}
    assert "GOV-NOLIMITS-MISSING-CODES" in codes
    assert "GOV-NOLIMITS-TOOL-MISMATCH" in codes
    assert "GOV-NOLIMITS-ADMIN-BYPASS" in codes


def test_auth_lifecycle_checker_profiles_and_federation(tmp_path: Path) -> None:
    runner = ConformanceRunner(tmp_path)
    assert [f.code for f in runner.run_standard("wellmanifest/auth-lifecycle")] == ["GOV-AUTH-LIFECYCLE-MISSING"]

    profile_path = tmp_path / ".governance" / "auth-lifecycle.json"
    valid_profile = {
        "schema": "wellmanifest.auth-lifecycle/profile/v1",
        "profileId": "otp-email",
        "emitsMembershipSignal": True,
        "authorityBoundary": {"issuesGrants": False, "home": "wellmanifest/authority-lifecycle"},
        "commercialBoundary": {
            "processesPayment": False,
            "consumesOnboardingProfile": "membership-before-payment",
            "home": "wellmanifest/saas-lifecycle",
        },
        "otpEmail": {"channel": "email"},
    }
    _write_json(profile_path, valid_profile)

    plane_path = tmp_path / "conformance" / "auth-lifecycle" / "plane.json"
    _write_json(plane_path, {
        "schema": "wellmanifest.auth-lifecycle/identity-plane/v1",
        "deployment": {"roleFromRequestHeaders": False, "dedicatedProcess": True, "dedicatedDataStore": True},
        "protocol": {
            "grantTypes": ["authorization_code", "refresh_token"],
            "pkceMethods": ["S256"],
            "oidcDiscovery": "/.well-known/openid-configuration",
            "problemDetails": True,
        },
        "errors": {"mediaType": "application/problem+json", "codes": ["AUTHN-001"], "traceparent": True},
        "sessions": {"cookieScope": "host-only", "httpOnly": True},
        "audit": {"failures": True, "secretsRedacted": True},
    })

    conn_path = tmp_path / "conformance" / "auth-lifecycle" / "connector.json"
    _write_json(conn_path, {
        "schema": "wellmanifest.auth-lifecycle/connector/v1",
        "authKind": "github-app-installation",
        "custody": {"vault": "envelope-encrypted", "exportRefreshToken": False, "consumerAccess": "token-exchange"},
        "webhooks": {"supported": True, "verification": "hmac-sha256"},
    })
    assert runner.run_standard("wellmanifest/auth-lifecycle") == []

    # Payment-as-membership receipt & unverified webhook connector must fail closed
    _write_json(profile_path, {
        "schema": "wellmanifest.auth-lifecycle/binding-receipt/v1",
        "profileId": "otp-email",
        "membershipVerified": True,
        "paymentNotImplied": False,
    })
    _write_json(conn_path, {
        "schema": "wellmanifest.auth-lifecycle/connector/v1",
        "authKind": "github-app-installation",
        "custody": {"vault": "envelope-encrypted", "exportRefreshToken": False, "consumerAccess": "token-exchange"},
        "webhooks": {"supported": True, "verification": "none"},
    })
    codes = {f.code for f in runner.run_standard("wellmanifest/auth-lifecycle")}
    assert "AUTHN-PAY-001" in codes
    assert "AUTHN-FED-006" in codes


def test_secrets_checker_envelopes_manifests_and_leases(tmp_path: Path) -> None:
    runner = ConformanceRunner(tmp_path)
    assert [f.code for f in runner.run_standard("wellmanifest/secrets")] == ["GOV-SECRETS-MISSING"]

    manifest_path = tmp_path / "vault-manifest.json"
    valid_manifest = {
        "schema": "wellmanifest.secrets/vault-manifest/v1",
        "version": 1,
        "entries": [
            {
                "id": "wfirma-prod",
                "origin": "https://api2.wfirma.pl",
                "scope": {"operations": ["invoice:read"], "targets": ["wfirma:invoices"]},
                "envelope": {
                    "schema": "wellmanifest.secrets/envelope/v1",
                    "version": 1,
                    "algorithm": "aes-256-gcm",
                    "iv": "aXY=",
                    "tag": "dGFn",
                    "ciphertext": "Y2lwaGVydGV4dA==",
                },
            }
        ],
    }
    _write_json(manifest_path, valid_manifest)
    lease_path = tmp_path / "conformance" / "secrets" / "lease.json"
    _write_json(lease_path, {
        "schema": "wellmanifest.secrets/lease/v1",
        "field": "api_key",
        "origin": "https://api2.wfirma.pl",
        "expires_in_seconds": 300,
    })
    assert runner.run_standard("wellmanifest/secrets") == []

    # Wildcard origin + insecure cipher must fail closed with exact codes
    bad_manifest = json.loads(json.dumps(valid_manifest))
    bad_manifest["entries"][0]["origin"] = "https://*.wfirma.pl"
    _write_json(manifest_path, bad_manifest)
    assert [f.code for f in runner.run_standard("wellmanifest/secrets")] == ["SECRET_ORIGIN_INVALID"]

    bad_cipher = json.loads(json.dumps(valid_manifest))
    bad_cipher["entries"][0]["envelope"]["algorithm"] = "aes-128-cbc"
    _write_json(manifest_path, bad_cipher)
    assert [f.code for f in runner.run_standard("wellmanifest/secrets")] == ["SECRET_CIPHER_UNSUPPORTED"]


def test_clonerd_checker_profile_and_environment_rules(tmp_path: Path) -> None:
    runner = ConformanceRunner(tmp_path)
    assert [f.code for f in runner.run_standard("wellmanifest/clonerd")] == ["GOV-CLONERD-MISSING"]

    profile_path = tmp_path / "profiles" / "clonerd.v1.json"
    _write_json(profile_path, {
        "schema": "wellmanifest.clonerd/profile/v1",
        "version": "0.1.0",
        "status": "experimental",
        "home": "wellmanifest",
        "shape": "domain_pack",
        "runtimeOwner": "clonerd-com",
        "presentation": {"authorityFromPresentation": False},
        "isolation": {
            "demoEffects": "forbidden",
            "tenantScope": "server-enforced",
            "cloudLocalFallback": "forbidden",
            "secretsInReceipts": "forbidden",
        },
        "contracts": {},
        "delivery": {},
        "continuation": {},
    })
    env_path = tmp_path / "clonerd.environment.json"
    _write_json(env_path, {
        "schema": "wellmanifest.clonerd/environment/v1",
        "name": "local-dev",
        "deployment": "local-simulator",
        "sourceRevision": "a" * 40,
        "endpoints": {
            "api": "http://127.0.0.1:8080",
            "identity": "http://localhost:8081",
            "device": "http://127.0.0.1:8082",
        },
        "auth": {"method": "user-session"},
        "acceptance": ["health"],
    })
    assert runner.run_standard("wellmanifest/clonerd") == []

    # Same simulator cookie hostname for identity & device -> CLONERD-ENV-005
    _write_json(env_path, {
        "schema": "wellmanifest.clonerd/environment/v1",
        "name": "local-dev",
        "deployment": "local-simulator",
        "sourceRevision": "a" * 40,
        "endpoints": {
            "api": "http://127.0.0.1:8080",
            "identity": "http://localhost:8081",
            "device": "http://localhost:8082",
        },
    })
    assert [f.code for f in runner.run_standard("wellmanifest/clonerd")] == ["CLONERD-ENV-005"]

    # Duplicate JSON key -> CLONERD-PROFILE-001
    env_path.write_text('{"schema": "wellmanifest.clonerd/environment/v1", "schema": "dup"}\n', encoding="utf-8")
    assert [f.code for f in runner.run_standard("wellmanifest/clonerd")] == ["CLONERD-PROFILE-001"]


def test_llm_account_tool_checker_profile_and_discovery_report(tmp_path: Path) -> None:
    runner = ConformanceRunner(tmp_path)
    assert [f.code for f in runner.run_standard("wellmanifest/llm-account-tool")] == ["GOV-LLM-ACCOUNT-MISSING"]

    prof_path = tmp_path / "llm-account-profile.json"
    _write_json(prof_path, {
        "id": "work-claude",
        "novnc_port": 6080,
        "providers": {"anthropic": {"account": "team"}},
        "attached_applications": [{"type": "cli", "command": "claude"}],
    })
    rep_path = tmp_path / "llm-discovery-report.json"
    _write_json(rep_path, {
        "schema_version": "llm-account-tool/v1",
        "host_id": "workstation-01",
        "credentials": [],
        "available_agents": ["claude", "codex"],
    })
    assert runner.run_standard("wellmanifest/llm-account-tool") == []

    # Invalid port (<1024) and malformed attached application
    _write_json(prof_path, {
        "id": "bad",
        "novnc_port": 80,
        "providers": {},
        "attached_applications": [{"type": "cli"}],
    })
    codes = {f.code for f in runner.run_standard("wellmanifest/llm-account-tool")}
    assert "GOV-LLM-ACCOUNT-PORT-INVALID" in codes
    assert "GOV-LLM-ACCOUNT-APP-INVALID" in codes
