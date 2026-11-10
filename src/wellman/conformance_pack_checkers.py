"""Deterministic static conformance checkers for S1 conformance-pack standards."""

from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from wellman.validator import Finding

REQUIRED_NOLIMITS_CODES = frozenset({
    "LIM-STORAGE-001", "LIM-TEST-002", "LIM-MERGE-003", "LIM-WORKTREE-004", "LIM-DEPENDENCY-005",
    "LIM-RESOURCE-006", "LIM-CONTEXT-007", "LIM-FLAKY-008", "LIM-GOVERNANCE-009", "LIM-COST-010",
})
AUTH_CLOSED_PROFILES = ("otp-email", "access-api", "session-continue")
AUTH_PLANE_SCHEMA = "wellmanifest.auth-lifecycle/identity-plane/v1"
AUTH_CONNECTOR_SCHEMA = "wellmanifest.auth-lifecycle/connector/v1"
AUTH_PROFILE_SCHEMA = "wellmanifest.auth-lifecycle/profile/v1"
AUTH_RECEIPT_SCHEMA = "wellmanifest.auth-lifecycle/binding-receipt/v1"
AUTH_ALLOWED_GRANTS = frozenset({
    "authorization_code", "refresh_token",
    "urn:ietf:params:oauth:grant-type:device_code", "urn:ietf:params:oauth:grant-type:token-exchange",
})
AUTH_CONNECTOR_KINDS = frozenset({
    "oauth2-authorization-code-pkce", "github-app-installation", "atlassian-oauth2-3lo", "scoped-api-token",
})
AUTH_WEBHOOK_VERIFICATIONS = frozenset({"hmac-sha256", "jwt", "shared-token"})
SECRET_ALLOWED_SCHEMES = frozenset({"https", "http", "imaps", "smtps", "postgres", "postgresql"})
SECRET_ALLOWED_CIPHERS = frozenset({"aes-256-gcm"})
SECRET_ALLOWED_FIELDS = frozenset({
    "api_key", "secret_key", "access_token", "username", "password", "app_key", "totp_seed",
})
SECRET_IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,159}$")
SECRET_SCOPE_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9._*:/-]{0,199}$")
CLONERD_SHA_RE = re.compile(r"^[a-f0-9]{40}$")
CLONERD_ENV_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
CLONERD_PROFILE_REQUIRED = frozenset({
    "schema", "version", "status", "home", "shape", "runtimeOwner",
    "presentation", "isolation", "contracts", "delivery", "continuation",
})


def _err(code: str, message: str, path: str, remediation: str) -> Finding:
    return Finding(code=code, message=message, severity="ERROR", path=path, remediation=remediation)


def _rel(root: Path, path: Path) -> str:
    return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)


def _unique_json_load(path: Path) -> Dict[str, Any]:
    def hook(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
        obj: Dict[str, Any] = {}
        for k, v in pairs:
            if k in obj:
                raise ValueError(f"duplicate JSON key '{k}'")
            obj[k] = v
        return obj

    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=hook)
    if not isinstance(data, dict):
        raise ValueError("expected top-level JSON object")
    return data


def _existing_files(root: Path, patterns: Iterable[str]) -> List[Path]:
    found: List[Path] = []
    for pat in patterns:
        for candidate in sorted(root.glob(pat)):
            if candidate.is_file() and candidate not in found:
                found.append(candidate)
    return found


def check_nolimits(root: Path) -> List[Finding]:
    """Validate wellmanifest/nolimits tool-bindings and remediation rules."""
    candidates = _existing_files(root, ("standard/tool-bindings.json", ".governance/nolimits.json", "nolimits.json"))
    if not candidates:
        return [_err(
            "GOV-NOLIMITS-MISSING",
            "Repository requires wellmanifest/nolimits but no tool-bindings or nolimits configuration was found.",
            "standard/tool-bindings.json",
            "Provide standard/tool-bindings.json or .governance/nolimits.json with canonical LIM-* bindings.",
        )]

    findings: List[Finding] = []
    for path in candidates:
        rel = _rel(root, path)
        try:
            doc = _unique_json_load(path)
        except Exception as exc:
            findings.append(_err("GOV-NOLIMITS-INVALID", f"Invalid NoLimits bindings JSON in {rel}: {exc}", rel,
                                 "Ensure valid JSON object without duplicate keys."))
            continue

        raw_bindings = doc.get("bindings")
        if not isinstance(raw_bindings, list) or not raw_bindings:
            findings.append(_err("GOV-NOLIMITS-INVALID", f"{rel} must declare a non-empty 'bindings' array.", rel,
                                 "Declare canonical LIM-* bindings under 'bindings'."))
            continue

        by_code: Dict[str, Dict[str, Any]] = {}
        req_fields = ("code", "name", "dimension", "remediationTool", "command", "evidenceRequired")
        for idx, item in enumerate(raw_bindings):
            if not isinstance(item, dict):
                findings.append(_err("GOV-NOLIMITS-BINDING-INVALID", f"Binding #{idx} in {rel} must be an object.", rel,
                                     "Provide code, name, dimension, remediationTool, command, and evidenceRequired."))
                continue
            missing_fields = [k for k in req_fields if not isinstance(item.get(k), str) or not item.get(k).strip()]
            if missing_fields:
                findings.append(_err(
                    "GOV-NOLIMITS-BINDING-INVALID",
                    f"Binding #{idx} in {rel} missing required string fields: {', '.join(missing_fields)}.",
                    rel, "Populate all required LimitBinding fields per wellmanifest/nolimits.",
                ))
                continue
            by_code[item["code"]] = item

        missing_codes = sorted(REQUIRED_NOLIMITS_CODES - set(by_code.keys()))
        if missing_codes:
            findings.append(_err(
                "GOV-NOLIMITS-MISSING-CODES",
                f"{rel} is missing canonical LIM-* codes: {', '.join(missing_codes)}.",
                rel, "Include all 10 canonical LIM-STORAGE-001..LIM-COST-010 limit bindings.",
            ))

        expected_tools = {
            "LIM-STORAGE-001": "semcod/fixos",
            "LIM-TEST-002": "semcod/testless",
            "LIM-MERGE-003": "subactor/validator-agent",
        }
        for code, expected_tool in expected_tools.items():
            entry = by_code.get(code)
            if entry and entry.get("remediationTool") != expected_tool:
                findings.append(_err(
                    "GOV-NOLIMITS-TOOL-MISMATCH",
                    f"{code} in {rel} must bind to '{expected_tool}', got '{entry.get('remediationTool')}'.",
                    rel, f"Bind {code} remediationTool to '{expected_tool}'.",
                ))
        merge_entry = by_code.get("LIM-MERGE-003")
        if merge_entry and "--admin" in merge_entry.get("command", ""):
            findings.append(_err(
                "GOV-NOLIMITS-ADMIN-BYPASS",
                f"LIM-MERGE-003 command in {rel} must never use --admin bypass.",
                rel, "Use independent subactor/validator-agent review and merge without --admin.",
            ))
    return findings


def _validate_auth_doc(doc: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    schema = doc.get("schema")
    if schema == AUTH_PROFILE_SCHEMA:
        profile_id = doc.get("profileId")
        if profile_id not in AUTH_CLOSED_PROFILES:
            return "AUTHN-PROFILE-001", f"Unknown auth-lifecycle profileId {profile_id!r}"
        if doc.get("emitsMembershipSignal") is not True:
            return "AUTHN-BOUND-001", "Auth profile requires emitsMembershipSignal=true"
        authority = doc.get("authorityBoundary") or {}
        if authority.get("issuesGrants") is not False or authority.get("home") != "wellmanifest/authority-lifecycle":
            return "AUTHN-BOUND-001", "authorityBoundary must set issuesGrants=false and home=wellmanifest/authority-lifecycle"
        commercial = doc.get("commercialBoundary") or {}
        if commercial.get("processesPayment") is not False:
            return "AUTHN-PAY-001", "AuthN profile must not process payment (processesPayment=false)"
        if (commercial.get("consumesOnboardingProfile") != "membership-before-payment"
                or commercial.get("home") != "wellmanifest/saas-lifecycle"):
            return "AUTHN-PAY-001", "commercialBoundary must adopt membership-before-payment from wellmanifest/saas-lifecycle"
        if profile_id == "otp-email" and (doc.get("otpEmail") or {}).get("channel") != "email":
            return "AUTHN-PROFILE-001", "otp-email profile requires otpEmail.channel='email'"
        return None

    if schema == AUTH_RECEIPT_SCHEMA:
        if doc.get("membershipVerified") is not True:
            return "AUTHN-BOUND-001", "Binding receipt requires membershipVerified=true"
        if doc.get("paymentNotImplied") is not True:
            return "AUTHN-PAY-001", "Binding receipt requires paymentNotImplied=true"
        if doc.get("profileId") not in AUTH_CLOSED_PROFILES:
            return "AUTHN-PROFILE-001", f"Unknown receipt profileId {doc.get('profileId')!r}"
        return None

    if schema == AUTH_PLANE_SCHEMA:
        dep = doc.get("deployment") or {}
        if (dep.get("roleFromRequestHeaders") is not False
                or dep.get("dedicatedProcess") is not True
                or dep.get("dedicatedDataStore") is not True):
            return "AUTHN-FED-001", "Identity plane requires dedicated process/store and roleFromRequestHeaders=false"
        proto = doc.get("protocol") or {}
        grants = proto.get("grantTypes") or []
        if (not isinstance(grants, list) or not grants
                or any(g not in AUTH_ALLOWED_GRANTS for g in grants)
                or proto.get("pkceMethods") != ["S256"]
                or proto.get("oidcDiscovery") != "/.well-known/openid-configuration"):
            return "AUTHN-FED-002", "Identity plane grantTypes, PKCE S256, or OIDC discovery contract invalid"
        errs, audit = doc.get("errors") or {}, doc.get("audit") or {}
        if (errs.get("mediaType") != "application/problem+json" or not errs.get("codes")
                or errs.get("traceparent") is not True or proto.get("problemDetails") is not True
                or audit.get("failures") is not True or audit.get("secretsRedacted") is not True):
            return "AUTHN-FED-004", "Identity plane requires problem+json errors, traceparent, and secret-redacted failure audit"
        sess = doc.get("sessions") or {}
        if sess.get("cookieScope") != "host-only" or sess.get("httpOnly") is not True:
            return "AUTHN-FED-005", "Identity plane sessions require cookieScope='host-only' and httpOnly=true"
        return None

    if schema == AUTH_CONNECTOR_SCHEMA:
        if doc.get("authKind") not in AUTH_CONNECTOR_KINDS:
            return "AUTHN-PROFILE-001", f"Unsupported connector authKind {doc.get('authKind')!r}"
        custody = doc.get("custody") or {}
        if (custody.get("vault") != "envelope-encrypted"
                or custody.get("exportRefreshToken") is not False
                or custody.get("consumerAccess") not in ("token-exchange", "broker-proxy")):
            return "AUTHN-FED-003", "Connector custody requires envelope-encrypted vault, exportRefreshToken=false, and brokered access"
        webhooks = doc.get("webhooks") or {}
        if webhooks.get("supported") and webhooks.get("verification") not in AUTH_WEBHOOK_VERIFICATIONS:
            return "AUTHN-FED-006", "Supported connector webhooks require hmac-sha256, jwt, or shared-token verification"
        return None

    return "AUTHN-PROFILE-001", f"Unsupported auth-lifecycle schema {schema!r}"


def check_auth_lifecycle(root: Path) -> List[Finding]:
    """Validate wellmanifest/auth-lifecycle profile, receipt, identity-plane, and connector descriptors."""
    discovered = _existing_files(root, (
        ".governance/auth-lifecycle.json", "auth-lifecycle.json",
        "standard/fixtures/valid/*.json", "conformance/auth-lifecycle/*.json",
    ))
    for candidate in _existing_files(root, ("profiles/*.json", "connectors/*.json")):
        if candidate not in discovered:
            try:
                probe = json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(probe, dict) and str(probe.get("schema", "")).startswith("wellmanifest.auth-lifecycle/"):
                discovered.append(candidate)

    if not discovered:
        return [_err(
            "GOV-AUTH-LIFECYCLE-MISSING",
            "Repository requires wellmanifest/auth-lifecycle but no auth-lifecycle profile or federation descriptor was found.",
            ".governance/auth-lifecycle.json",
            "Add an auth-lifecycle profile, identity-plane, or connector JSON descriptor.",
        )]

    findings: List[Finding] = []
    for path in discovered:
        rel = _rel(root, path)
        try:
            doc = _unique_json_load(path)
        except Exception as exc:
            findings.append(_err("AUTHN-PROFILE-001", f"Invalid auth-lifecycle JSON in {rel}: {exc}", rel,
                                 "Fix JSON syntax and remove duplicate keys."))
            continue
        err = _validate_auth_doc(doc)
        if err is not None:
            findings.append(_err(err[0], f"{rel}: {err[1]}", rel,
                                 "Align descriptor with wellmanifest/auth-lifecycle closed profile and federation invariants."))
    return findings


def _validate_secret_origin(origin: str) -> Optional[str]:
    if not origin or "*" in origin:
        return f"Wildcard or empty origin not allowed: {origin!r}"
    parsed = urllib.parse.urlsplit(origin)
    if parsed.scheme not in SECRET_ALLOWED_SCHEMES:
        return f"Unsupported scheme in origin: {parsed.scheme!r}"
    if not parsed.netloc:
        return f"Origin missing host/netloc: {origin!r}"
    if parsed.username or parsed.password:
        return "Origin must not contain user credentials"
    if parsed.query or parsed.fragment:
        return "Origin must not contain query or fragment"
    if parsed.path and parsed.path != "/":
        return f"Origin must not contain URL path: {parsed.path!r}"
    return None


def _validate_secret_envelope(doc: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    if doc.get("schema") != "wellmanifest.secrets/envelope/v1" or doc.get("version") != 1:
        return "SECRET_ENVELOPE_INVALID", "Envelope requires schema='wellmanifest.secrets/envelope/v1' and version=1"
    if doc.get("algorithm") not in SECRET_ALLOWED_CIPHERS:
        return "SECRET_CIPHER_UNSUPPORTED", f"Disallowed cipher: {doc.get('algorithm')!r}"
    for field in ("iv", "tag", "ciphertext"):
        if not isinstance(doc.get(field), str) or not doc.get(field):
            return "SECRET_ENVELOPE_INVALID", f"Envelope missing required field: {field}"
    return None


def _validate_secrets_doc(doc: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    schema = doc.get("schema")
    if schema == "wellmanifest.secrets/envelope/v1":
        return _validate_secret_envelope(doc)
    if schema == "wellmanifest.secrets/vault-manifest/v1":
        if doc.get("version") != 1 or not isinstance(doc.get("entries"), list):
            return "SECRET_ENVELOPE_INVALID", "Vault manifest requires version=1 and an 'entries' array"
        for entry in doc["entries"]:
            if not isinstance(entry, dict) or not SECRET_IDENTIFIER_RE.match(str(entry.get("id", ""))):
                return "SECRET_ENVELOPE_INVALID", f"Invalid vault manifest entry id: {entry.get('id') if isinstance(entry, dict) else entry!r}"
            origin_err = _validate_secret_origin(str(entry.get("origin") or ""))
            if origin_err:
                return "SECRET_ORIGIN_INVALID", origin_err
            scope = entry.get("scope") or {}
            ops, targets = scope.get("operations"), scope.get("targets")
            if (not isinstance(ops, list) or not ops or not isinstance(targets, list) or not targets
                    or any(not SECRET_SCOPE_TOKEN_RE.match(str(op)) for op in ops)
                    or any(not SECRET_SCOPE_TOKEN_RE.match(str(t)) for t in targets)):
                return "SECRET_SCOPE_DENIED", "Vault entry scope requires valid non-empty operations and targets"
            env = entry.get("envelope")
            if not isinstance(env, dict):
                return "SECRET_ENVELOPE_INVALID", "Vault entry missing envelope object"
            env_err = _validate_secret_envelope(env)
            if env_err:
                return env_err
        return None
    if schema == "wellmanifest.secrets/lease/v1":
        if doc.get("field") not in SECRET_ALLOWED_FIELDS:
            return "SECRET_ENVELOPE_INVALID", f"Disallowed secret lease field: {doc.get('field')!r}"
        origin_err = _validate_secret_origin(str(doc.get("origin") or ""))
        if origin_err:
            return "SECRET_ORIGIN_INVALID", origin_err
        ttl = doc.get("expires_in_seconds")
        if isinstance(ttl, bool) or not isinstance(ttl, int) or ttl < 5 or ttl > 86400:
            return "SECRET_ENVELOPE_INVALID", f"Invalid secret lease expires_in_seconds: {ttl!r}"
        return None
    return "SECRET_ENVELOPE_INVALID", f"Unknown secrets schema {schema!r}"


def check_secrets(root: Path) -> List[Finding]:
    """Validate wellmanifest/secrets envelopes, vault manifests, and bounded secret leases."""
    candidates = _existing_files(root, (
        ".governance/vault-manifest.json", "vault-manifest.json", ".governance/secrets.json",
        "standard/fixtures/valid/*.json", "conformance/secrets/*.json",
    ))
    if not candidates:
        return [_err(
            "GOV-SECRETS-MISSING",
            "Repository requires wellmanifest/secrets but no vault-manifest, envelope, or lease descriptor was found.",
            "vault-manifest.json",
            "Provide a vault-manifest.json, credential envelope, or secret lease conforming to wellmanifest/secrets.",
        )]

    findings: List[Finding] = []
    for path in candidates:
        rel = _rel(root, path)
        try:
            doc = _unique_json_load(path)
        except Exception as exc:
            findings.append(_err("SECRET_ENVELOPE_INVALID", f"Invalid secrets JSON in {rel}: {exc}", rel,
                                 "Ensure valid JSON object without duplicate keys."))
            continue
        err = _validate_secrets_doc(doc)
        if err is not None:
            findings.append(_err(err[0], f"{rel}: {err[1]}", rel,
                                 "Use aes-256-gcm envelopes, strict scheme://host origins without wildcards/paths, and bounded leases."))
    return findings


def _validate_clonerd_doc(doc: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    schema = doc.get("schema")
    if schema == "wellmanifest.clonerd/profile/v1":
        if not CLONERD_PROFILE_REQUIRED <= doc.keys():
            missing = sorted(CLONERD_PROFILE_REQUIRED - doc.keys())
            return "CLONERD-PROFILE-001", f"Missing required profile fields: {', '.join(missing)}"
        pres, iso = doc.get("presentation") or {}, doc.get("isolation") or {}
        if (not isinstance(pres, dict) or pres.get("authorityFromPresentation") is not False
                or not isinstance(iso, dict) or iso.get("demoEffects") != "forbidden"
                or iso.get("cloudLocalFallback") != "forbidden" or iso.get("secretsInReceipts") != "forbidden"):
            return "CLONERD-PROFILE-001", "Clonerd profile violates presentation authority or isolation invariants"
        return None

    if schema == "wellmanifest.clonerd/environment/v1":
        deployment = doc.get("deployment")
        if (not CLONERD_ENV_NAME_RE.match(str(doc.get("name", "")))
                or deployment not in ("local-simulator", "self-hosted", "existing-service")
                or not CLONERD_SHA_RE.match(str(doc.get("sourceRevision", "")))):
            return "CLONERD-PROFILE-001", "Clonerd environment requires valid name, deployment, and 40-hex sourceRevision"
        endpoints = doc.get("endpoints")
        if not isinstance(endpoints, dict) or "api" not in endpoints or "identity" not in endpoints:
            return "CLONERD-PROFILE-001", "Clonerd environment requires 'api' and 'identity' endpoints"
        local = deployment == "local-simulator"
        if local and "device" not in endpoints:
            return "CLONERD-ENV-001", "Simulator environment requires 'device' endpoint"
        for url in endpoints.values():
            if not isinstance(url, str):
                return "CLONERD-ENV-002", "Endpoint URL must be a string"
            parsed = urllib.parse.urlsplit(url)
            if (parsed.username or parsed.password or parsed.query or parsed.fragment
                    or parsed.path not in ("", "/") or not parsed.hostname):
                return "CLONERD-ENV-002", f"Expected origin without secrets, query, or API path: {url!r}"
            if local:
                if parsed.scheme not in ("http", "https") or parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
                    return "CLONERD-ENV-003", f"Simulator endpoint must stay on loopback: {url!r}"
            elif parsed.scheme != "https":
                return "CLONERD-ENV-004", f"Non-simulator service endpoint requires HTTPS: {url!r}"
        if local and urllib.parse.urlsplit(endpoints["identity"]).hostname == urllib.parse.urlsplit(endpoints["device"]).hostname:
            return "CLONERD-ENV-005", "Simulator requires separate identity and device cookie hostnames"
        return None

    return "CLONERD-PROFILE-001", f"Unsupported clonerd schema {schema!r}"


def check_clonerd(root: Path) -> List[Finding]:
    """Validate wellmanifest/clonerd composition profiles and environment descriptors."""
    candidates = _existing_files(root, (
        "profiles/clonerd.v1.json", ".governance/clonerd.json", "clonerd.profile.json",
        "clonerd.environment.json", "environments/*.json", "conformance/clonerd/*.json",
    ))
    if not candidates:
        return [_err(
            "GOV-CLONERD-MISSING",
            "Repository requires wellmanifest/clonerd but no clonerd profile or environment descriptor was found.",
            "profiles/clonerd.v1.json", "Provide profiles/clonerd.v1.json or a clonerd.environment.json descriptor.",
        )]

    findings: List[Finding] = []
    for path in candidates:
        rel = _rel(root, path)
        try:
            doc = _unique_json_load(path)
        except Exception as exc:
            findings.append(_err("CLONERD-PROFILE-001", f"Invalid clonerd JSON in {rel}: {exc}", rel,
                                 "Fix JSON syntax and ensure no duplicate JSON keys."))
            continue
        err = _validate_clonerd_doc(doc)
        if err is not None:
            findings.append(_err(err[0], f"{rel}: {err[1]}", rel,
                                 "Satisfy clonerd profile isolation, origin hygiene, loopback/HTTPS, and cookie-hostname separation rules."))
    return findings


def _validate_llm_account_doc(doc: Dict[str, Any]) -> List[Tuple[str, str]]:
    errors: List[Tuple[str, str]] = []
    if "schema_version" in doc or "available_agents" in doc or "host_id" in doc:
        if doc.get("schema_version") != "llm-account-tool/v1":
            errors.append(("GOV-LLM-ACCOUNT-REPORT-INVALID", f"Invalid schema_version: {doc.get('schema_version')!r}"))
        if not isinstance(doc.get("host_id"), str) or not doc.get("host_id"):
            errors.append(("GOV-LLM-ACCOUNT-REPORT-INVALID", "Discovery report missing required 'host_id'"))
        if not isinstance(doc.get("credentials"), list):
            errors.append(("GOV-LLM-ACCOUNT-REPORT-INVALID", "Discovery report missing required 'credentials' list"))
        if not isinstance(doc.get("available_agents"), list):
            errors.append(("GOV-LLM-ACCOUNT-REPORT-INVALID", "Discovery report missing required 'available_agents' list"))
        return errors

    if not isinstance(doc.get("id"), str) or not doc.get("id"):
        errors.append(("GOV-LLM-ACCOUNT-PROFILE-INVALID", "Profile missing required 'id'"))
    port = doc.get("novnc_port")
    if isinstance(port, bool) or not isinstance(port, int) or not (1024 <= port <= 65535):
        errors.append(("GOV-LLM-ACCOUNT-PORT-INVALID", f"Invalid or missing novnc_port: {port!r} (must be 1024-65535)"))
    if not isinstance(doc.get("providers"), dict):
        errors.append(("GOV-LLM-ACCOUNT-PROFILE-INVALID", "Profile missing required 'providers' dictionary"))
    apps = doc.get("attached_applications", [])
    if not isinstance(apps, list):
        errors.append(("GOV-LLM-ACCOUNT-PROFILE-INVALID", "'attached_applications' must be a list"))
    else:
        for idx, app in enumerate(apps):
            if not isinstance(app, dict) or not app.get("type") or not app.get("command"):
                errors.append(("GOV-LLM-ACCOUNT-APP-INVALID", f"Attached application #{idx} requires non-empty 'type' and 'command'"))
    return errors


def check_llm_account_tool(root: Path) -> List[Finding]:
    """Validate wellmanifest/llm-account-tool profiles, discovery reports, or pack schema."""
    candidates = _existing_files(root, (
        ".governance/llm-account-tool.json", "llm-account-profile.json",
        "llm-discovery-report.json", "conformance/llm-account-tool/*.json",
    ))
    schema_path = root / "standard" / "llm-account-tool.schema.json"
    if not candidates and not schema_path.is_file():
        return [_err("GOV-LLM-ACCOUNT-MISSING",
                     "Repository requires wellmanifest/llm-account-tool but no profile, discovery report, or schema was found.",
                     "llm-account-profile.json",
                     "Provide llm-account-profile.json, llm-discovery-report.json, or standard/llm-account-tool.schema.json.")]
    findings: List[Finding] = []
    if schema_path.is_file():
        rel_schema = _rel(root, schema_path)
        try:
            sdoc = _unique_json_load(schema_path)
            if sdoc.get("type") != "object" and "$defs" not in sdoc and "properties" not in sdoc:
                findings.append(_err("GOV-LLM-ACCOUNT-SCHEMA-INVALID", f"{rel_schema} is not a valid JSON Schema object.",
                                     rel_schema, "Ensure standard/llm-account-tool.schema.json defines a valid JSON Schema."))
        except Exception as exc:
            findings.append(_err("GOV-LLM-ACCOUNT-SCHEMA-INVALID", f"Invalid JSON in {rel_schema}: {exc}",
                                 rel_schema, "Fix JSON syntax in standard/llm-account-tool.schema.json."))
    for path in candidates:
        rel = _rel(root, path)
        try:
            doc = _unique_json_load(path)
        except Exception as exc:
            findings.append(_err("GOV-LLM-ACCOUNT-PROFILE-INVALID", f"Invalid llm-account-tool JSON in {rel}: {exc}",
                                 rel, "Fix JSON syntax and remove duplicate keys."))
            continue
        for code, msg in _validate_llm_account_doc(doc):
            findings.append(_err(code, f"{rel}: {msg}", rel,
                                 "Conform to wellmanifest/llm-account-tool profile (id, novnc_port 1024-65535, providers) or discovery report v1."))
    return findings
