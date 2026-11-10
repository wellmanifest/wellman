"""Dependency-free S1 static conformance checkers for the remaining 14 catalog standards.

Covers:
- wellmanifest/authority-lifecycle
- wellmanifest/repair-lifecycle
- wellmanifest/account-runtime
- wellmanifest/skills
- wellmanifest/status
- wellmanifest/performance
- wellmanifest/llm
- wellmanifest/dsl
- wellmanifest/env-dsl
- wellmanifest/code-dsl
- wellmanifest/nl-dsl-llm
- wellmanifest/nl-api-llm
- wellmanifest/poa
- wellmanifest/anonym
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from wellman.validator import Finding

_MAX_FILE_BYTES = 2 * 1024 * 1024
_SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA256_URI_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ENV_VAR_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_STABLE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
_SECRET_MATERIAL_RE = re.compile(
    r"(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{20,}|\bsk-[A-Za-z0-9_-]{20,})",
    re.IGNORECASE,
)
_SKILL_EXEC_INJECTION_RE = re.compile(
    r"(?:-----BEGIN|\b(?:ba)?sh\s+-c\b|\bcurl\s+https?://|\bwget\s+https?://|\$\()",
    re.IGNORECASE,
)
_LLM_CANONICAL_OPS = frozenset({
    "profile.resolve",
    "knowledge.resolve",
    "artifact.resolve",
    "observation.read",
    "research.plan",
    "llm.invoke",
    "validation.run",
    "receipt.write",
})
_CHANGE_LEASE_PHASES = frozenset({
    "allocated",
    "claimed",
    "active",
    "publication_frozen",
    "released",
    "closed",
    "cancelled",
    "expired",
})
_API_PROTOCOLS = frozenset({"rest", "graphql", "grpc", "mcp", "cli", "websocket", "http", "https"})


def _err(code: str, message: str, path: str, remediation: str) -> Finding:
    return Finding(code=code, message=message, severity="ERROR", path=path, remediation=remediation)


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


def _has_symlink_component(root: Path, candidate: Path) -> bool:
    if candidate.is_symlink():
        return True
    try:
        rel = candidate.relative_to(root)
    except ValueError:
        return True
    cur = root
    for part in rel.parts:
        cur = cur / part
        if cur.is_symlink():
            return True
    return False


def _read_bounded_text(root: Path, path: Path) -> Tuple[Optional[str], Optional[str]]:
    if _has_symlink_component(root, path):
        return None, "refusing symlinked path"
    try:
        st = path.stat()
    except OSError as exc:
        return None, f"cannot stat file: {exc}"
    if st.st_size > _MAX_FILE_BYTES:
        return None, f"file exceeds {_MAX_FILE_BYTES} byte limit ({st.st_size} bytes)"
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, f"cannot read file: {exc}"
    if len(raw) > _MAX_FILE_BYTES:
        return None, f"file exceeds {_MAX_FILE_BYTES} byte limit"
    try:
        return raw.decode("utf-8"), None
    except UnicodeDecodeError as exc:
        return None, f"invalid UTF-8: {exc}"


def _load_unique_json(root: Path, path: Path, error_code: str, remediation: str) -> Tuple[Optional[Dict[str, Any]], Optional[Finding]]:
    rel = _rel(root, path)
    text, err = _read_bounded_text(root, path)
    if err is not None or text is None:
        return None, _err(error_code, f"Cannot read {rel}: {err}", rel, remediation)

    def _hook(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
        obj: Dict[str, Any] = {}
        for k, v in pairs:
            if k in obj:
                raise ValueError(f"duplicate JSON key '{k}'")
            obj[k] = v
        return obj

    try:
        doc = json.loads(text, object_pairs_hook=_hook)
    except Exception as exc:
        return None, _err(error_code, f"Invalid JSON in {rel}: {exc}", rel, remediation)
    if not isinstance(doc, dict):
        return None, _err(error_code, f"{rel} must contain a top-level JSON object.", rel, remediation)
    return doc, None


def _discover_candidates(root: Path, patterns: Iterable[str]) -> List[Path]:
    found: List[Path] = []
    for pat in patterns:
        for candidate in sorted(root.glob(pat)):
            if (candidate.is_file() or candidate.is_symlink()) and candidate not in found:
                parts = candidate.relative_to(root).parts if candidate.is_relative_to(root) else ()
                if any(p in {".git", ".worktrees", "node_modules", ".venv", "venv", "__pycache__"} for p in parts):
                    continue
                found.append(candidate)
    return found


def _valid_tz_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value or len(value) > 64:
        return False
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return dt.tzinfo is not None


def check_authority_lifecycle(root: Path) -> List[Finding]:
    """Validate wellmanifest/authority-lifecycle leases, grants, and fencing contracts."""
    candidates = _discover_candidates(root, (
        ".governance/authority-lifecycle.json",
        "authority-lifecycle.json",
        "profiles/*authority*.json",
        ".subactor/leases/*.json",
    ))
    if not candidates:
        return [_err(
            "GOV-AUTHORITY-LIFECYCLE-MISSING",
            "Repository requires wellmanifest/authority-lifecycle but no lease or authority-lifecycle profile was found.",
            ".governance/authority-lifecycle.json",
            "Provide .governance/authority-lifecycle.json or canonical .subactor/leases/*.json change-lease records.",
        )]

    findings: List[Finding] = []
    for path in candidates:
        rel = _rel(root, path)
        doc, load_err = _load_unique_json(
            root, path, "GOV-AUTHORITY-LIFECYCLE-INVALID",
            "Provide a bounded, non-symlinked authority-lifecycle or change-lease JSON object.",
        )
        if load_err is not None or doc is None:
            findings.append(load_err)  # type: ignore[arg-type]
            continue

        schema = doc.get("schema")
        if schema == "wellmanifest.change-lease/v1":
            for field in ("leaseId", "ticketId", "ownerActor", "ownerSession", "phase"):
                if not isinstance(doc.get(field), str) or not doc[field].strip():
                    findings.append(_err(
                        "GOV-AUTHORITY-LIFECYCLE-INVALID",
                        f"Change lease {rel} is missing non-empty string field '{field}'.",
                        rel, "Include leaseId, ticketId, ownerActor, ownerSession, and phase.",
                    ))
            if doc.get("phase") not in _CHANGE_LEASE_PHASES:
                findings.append(_err(
                    "GOV-AUTHORITY-LIFECYCLE-INVALID",
                    f"Change lease {rel} has unsupported phase '{doc.get('phase')}'.",
                    rel, f"Use a canonical change-lease phase: {', '.join(sorted(_CHANGE_LEASE_PHASES))}.",
                ))
            for token_field in ("leaseRevision", "fencingToken"):
                val = doc.get(token_field)
                if type(val) is not int or val < 1:
                    findings.append(_err(
                        "GOV-AUTHORITY-LIFECYCLE-FENCING",
                        f"Change lease {rel} must declare positive integer '{token_field}'.",
                        rel, "Ensure monotonic positive integer leaseRevision and fencingToken.",
                    ))
            for ts_field in ("issuedAt", "expiresAt"):
                if not _valid_tz_datetime(doc.get(ts_field)):
                    findings.append(_err(
                        "GOV-AUTHORITY-LIFECYCLE-EXPIRY",
                        f"Change lease {rel} has missing or non-timezone timestamp '{ts_field}'.",
                        rel, "Use ISO-8601 UTC timestamps for issuedAt and expiresAt.",
                    ))
        elif schema in {"wellmanifest.authority-lifecycle/grant/v1", "wellmanifest.authority-lifecycle/profile/v1", "wellmanifest.authority-lifecycle/v1"}:
            principal = doc.get("principal")
            if not isinstance(principal, dict) or not str(principal.get("uri", "")).startswith("authority://principal/"):
                findings.append(_err(
                    "GOV-AUTHORITY-LIFECYCLE-INVALID",
                    f"Authority document {rel} must declare principal.uri starting with 'authority://principal/'.",
                    rel, "Bind principal.uri to authority://principal/<id> with a declared principal kind.",
                ))
            fencing = doc.get("fencingToken", 1)
            if type(fencing) is not int or fencing < 1:
                findings.append(_err(
                    "GOV-AUTHORITY-LIFECYCLE-FENCING",
                    f"Authority document {rel} must declare positive integer fencingToken.",
                    rel, "Set fencingToken >= 1.",
                ))
        else:
            findings.append(_err(
                "GOV-AUTHORITY-LIFECYCLE-INVALID",
                f"Unrecognized schema '{schema}' in {rel}.",
                rel, "Use wellmanifest.change-lease/v1 or wellmanifest.authority-lifecycle/grant/v1.",
            ))
    return findings


def check_repair_lifecycle(root: Path) -> List[Finding]:
    """Validate wellmanifest/repair-lifecycle remediation intents and repair cases."""
    candidates = _discover_candidates(root, (
        ".governance/remediation-intent.json",
        ".governance/repair-lifecycle.json",
        "repair-lifecycle.json",
        "profiles/*repair*.json",
    ))
    if not candidates:
        return [_err(
            "GOV-REPAIR-LIFECYCLE-MISSING",
            "Repository requires wellmanifest/repair-lifecycle but no remediation-intent or repair-lifecycle contract was found.",
            ".governance/repair-lifecycle.json",
            "Provide .governance/repair-lifecycle.json or .governance/remediation-intent.json.",
        )]

    findings: List[Finding] = []
    for path in candidates:
        rel = _rel(root, path)
        doc, load_err = _load_unique_json(
            root, path, "GOV-REPAIR-LIFECYCLE-INVALID",
            "Provide a valid repair-lifecycle or remediation-intent JSON object.",
        )
        if load_err is not None or doc is None:
            findings.append(load_err)  # type: ignore[arg-type]
            continue

        schema = doc.get("schema")
        if schema in {"new-project.remediation-intent/v1", "wellmanifest.remediation-intent/v1"}:
            if not isinstance(doc.get("diagnosticCode") or doc.get("code") or doc.get("problem"), (str, dict)):
                findings.append(_err(
                    "GOV-REPAIR-LIFECYCLE-INVALID",
                    f"Remediation intent {rel} must bind a diagnosticCode, code, or problem object.",
                    rel, "Declare diagnosticCode and bounded remediation steps.",
                ))
            steps = doc.get("steps") or doc.get("actions")
            if not isinstance(steps, list) or not steps:
                findings.append(_err(
                    "GOV-REPAIR-LIFECYCLE-INVALID",
                    f"Remediation intent {rel} must declare a non-empty 'steps' or 'actions' list.",
                    rel, "Specify deterministic remediation steps.",
                ))
        elif schema in {"wellmanifest.repair-lifecycle/case/v1", "wellmanifest.repair-lifecycle/profile/v1", "wellmanifest.repair-lifecycle/v1"}:
            problem = doc.get("problem")
            if not isinstance(problem, dict) or not str(problem.get("diagnosticId", "")).startswith("repair://diagnostic/"):
                findings.append(_err(
                    "GOV-REPAIR-LIFECYCLE-INVALID",
                    f"Repair case {rel} must declare problem.diagnosticId starting with 'repair://diagnostic/'.",
                    rel, "Bind problem.diagnosticId to repair://diagnostic/<id> with observationOnly=true.",
                ))
            elif problem.get("observationOnly") is not True:
                findings.append(_err(
                    "GOV-REPAIR-LIFECYCLE-OBSERVATION",
                    f"Repair case {rel} problem.observationOnly must be true.",
                    rel, "Keep diagnostic intake observation-only (problem.observationOnly = true).",
                ))
        else:
            findings.append(_err(
                "GOV-REPAIR-LIFECYCLE-INVALID",
                f"Unsupported repair-lifecycle schema '{schema}' in {rel}.",
                rel, "Use wellmanifest.repair-lifecycle/case/v1 or new-project.remediation-intent/v1.",
            ))
    return findings


def check_account_runtime(root: Path) -> List[Finding]:
    """Validate wellmanifest/account-runtime and service-access secret-free contracts."""
    candidates = _discover_candidates(root, (
        "standard/account-runtime.json",
        "standard/service-access.json",
        ".governance/account-runtime.json",
        ".governance/service-access.json",
        "account-runtime.json",
        "service-access.json",
    ))
    if not candidates:
        return [_err(
            "GOV-ACCOUNT-RUNTIME-MISSING",
            "Repository requires wellmanifest/account-runtime but no account-runtime or service-access descriptor was found.",
            ".governance/account-runtime.json",
            "Provide .governance/account-runtime.json or service-access.json.",
        )]

    allowed_schemas = {
        "https://wellmanifest.dev/schemas/account-runtime/v1",
        "wellmanifest.account-runtime/v1",
        "https://wellmanifest.dev/schemas/service-access/v1",
        "wellmanifest.service-access/v1",
    }
    findings: List[Finding] = []
    for path in candidates:
        rel = _rel(root, path)
        raw_text, raw_err = _read_bounded_text(root, path)
        if raw_err is None and raw_text is not None and _SECRET_MATERIAL_RE.search(raw_text):
            findings.append(_err(
                "GOV-ACCOUNT-RUNTIME-SECRET",
                f"{rel} contains embedded secret material violating the secret-free account-runtime boundary.",
                rel, "Replace inline credentials with vault:// or secret-lease references.",
            ))
        doc, load_err = _load_unique_json(
            root, path, "GOV-ACCOUNT-RUNTIME-INVALID",
            "Provide valid UTF-8 JSON without duplicate keys.",
        )
        if load_err is not None or doc is None:
            findings.append(load_err)  # type: ignore[arg-type]
            continue
        schema = doc.get("schema") or doc.get("$schema")
        if schema not in allowed_schemas:
            findings.append(_err(
                "GOV-ACCOUNT-RUNTIME-INVALID",
                f"{rel} must declare a canonical account-runtime or service-access v1 schema.",
                rel, "Set schema to 'wellmanifest.account-runtime/v1' or 'wellmanifest.service-access/v1'.",
            ))
        collection = doc.get("accounts") or doc.get("identities") or doc.get("services") or doc.get("bindings")
        if not isinstance(collection, list) or not collection:
            findings.append(_err(
                "GOV-ACCOUNT-RUNTIME-INVALID",
                f"{rel} must declare a non-empty accounts, identities, services, or bindings array.",
                rel, "Declare at least one governed account or service-access binding.",
            ))
    return findings


def check_skills(root: Path) -> List[Finding]:
    """Validate wellmanifest/skills JSON descriptors and SKILL.md frontmatter contracts."""
    json_candidates = _discover_candidates(root, (
        "standard/skill.json",
        ".governance/skills.json",
        "skills.json",
        "skills/**/skill.json",
    ))
    md_candidates = _discover_candidates(root, (
        "SKILL.md",
        "skills/**/SKILL.md",
    ))
    if not json_candidates and not md_candidates:
        return [_err(
            "GOV-SKILLS-MISSING",
            "Repository requires wellmanifest/skills but no skill.json or SKILL.md artifact was found.",
            "skills/SKILL.md",
            "Provide skills/<name>/SKILL.md with YAML frontmatter or standard/skill.json.",
        )]

    findings: List[Finding] = []
    for path in json_candidates:
        rel = _rel(root, path)
        doc, load_err = _load_unique_json(
            root, path, "GOV-SKILLS-INVALID",
            "Provide valid skill JSON without duplicate keys.",
        )
        if load_err is not None or doc is None:
            findings.append(load_err)  # type: ignore[arg-type]
            continue
        if not isinstance(doc.get("id") or doc.get("name"), str) or not str(doc.get("id") or doc.get("name")).strip():
            findings.append(_err(
                "GOV-SKILLS-INVALID",
                f"Skill descriptor {rel} must declare a non-empty 'id' or 'name'.",
                rel, "Populate skill id/name and operations/tools.",
            ))
        ops = doc.get("operations") or doc.get("tools") or doc.get("skills")
        if not isinstance(ops, list) or not ops:
            findings.append(_err(
                "GOV-SKILLS-INVALID",
                f"Skill descriptor {rel} must declare a non-empty operations, tools, or skills list.",
                rel, "Declare governed skill operations or tool interfaces.",
            ))
        desc = str(doc.get("description", ""))
        if _SKILL_EXEC_INJECTION_RE.search(desc):
            findings.append(_err(
                "GOV-SKILLS-INJECTION",
                f"Skill descriptor {rel} contains executable shell or secret material in description prose.",
                rel, "Keep skill descriptions declarative and free of shell command injection.",
            ))

    for path in md_candidates:
        rel = _rel(root, path)
        text, err = _read_bounded_text(root, path)
        if err is not None or text is None:
            findings.append(_err("GOV-SKILLS-INVALID", f"Cannot read {rel}: {err}", rel, "Ensure SKILL.md is a bounded UTF-8 file."))
            continue
        if not text.startswith("---\n"):
            findings.append(_err(
                "GOV-SKILLS-FRONTMATTER",
                f"{rel} is missing required YAML frontmatter ('---').",
                rel, "Add YAML frontmatter with 'name' and 'description' to SKILL.md.",
            ))
            continue
        end_idx = text.find("\n---", 4)
        if end_idx == -1:
            findings.append(_err(
                "GOV-SKILLS-FRONTMATTER",
                f"{rel} has unclosed YAML frontmatter.",
                rel, "Close YAML frontmatter with '---'.",
            ))
            continue
        header = text[4:end_idx]
        keys = {
            line.split(":", 1)[0].strip(): line.split(":", 1)[1].strip()
            for line in header.splitlines()
            if ":" in line and not line.lstrip().startswith("#")
        }
        for req_key in ("name", "description"):
            if not keys.get(req_key):
                findings.append(_err(
                    "GOV-SKILLS-FRONTMATTER",
                    f"{rel} frontmatter is missing non-empty '{req_key}'.",
                    rel, "Declare both 'name' and 'description' in SKILL.md frontmatter.",
                ))
    return findings


def check_status(root: Path) -> List[Finding]:
    """Validate wellmanifest/status contract bundles and transition graph invariants."""
    candidates = _discover_candidates(root, (
        "contracts/status.contract.json",
        ".governance/status.json",
        "status.contract.json",
        "status.json",
    ))
    if not candidates:
        return [_err(
            "GOV-STATUS-MISSING",
            "Repository requires wellmanifest/status but no status contract bundle was found.",
            "contracts/status.contract.json",
            "Provide contracts/status.contract.json or .governance/status.json.",
        )]

    findings: List[Finding] = []
    for path in candidates:
        rel = _rel(root, path)
        doc, load_err = _load_unique_json(
            root, path, "GOV-STATUS-INVALID",
            "Provide a valid status contract JSON object.",
        )
        if load_err is not None or doc is None:
            findings.append(load_err)  # type: ignore[arg-type]
            continue
        if doc.get("schema") not in {"wellmanifest.status/contract-bundle/v1", "wellmanifest.status/v1"}:
            findings.append(_err(
                "GOV-STATUS-INVALID",
                f"{rel} must declare schema 'wellmanifest.status/contract-bundle/v1' or 'wellmanifest.status/v1'.",
                rel, "Set canonical wellmanifest.status schema.",
            ))
        if "modelAuthority" in doc and doc["modelAuthority"] != "propose-only":
            findings.append(_err(
                "GOV-STATUS-AUTHORITY",
                f"{rel} modelAuthority must be 'propose-only', got '{doc['modelAuthority']}'.",
                rel, "Restrict modelAuthority to 'propose-only' so runtime owns committed status transitions.",
            ))
        profiles = doc.get("profiles")
        if not isinstance(profiles, dict) or not profiles:
            findings.append(_err(
                "GOV-STATUS-INVALID",
                f"{rel} must declare a non-empty 'profiles' state-machine mapping.",
                rel, "Define at least one status profile with initial, states, terminal, and transitions.",
            ))
            continue
        for prof_name, prof in profiles.items():
            if not isinstance(prof, dict):
                findings.append(_err("GOV-STATUS-INVALID", f"Profile '{prof_name}' in {rel} must be an object.", rel, "Define states and transitions."))
                continue
            states = prof.get("states")
            initial = prof.get("initial")
            terminal = prof.get("terminal", [])
            transitions = prof.get("transitions")
            if not isinstance(states, list) or not states or not all(isinstance(s, str) and s for s in states):
                findings.append(_err("GOV-STATUS-INVALID", f"Profile '{prof_name}' in {rel} must list non-empty string states.", rel, "Populate states list."))
                continue
            state_set = set(states)
            if initial not in state_set:
                findings.append(_err("GOV-STATUS-GRAPH", f"Profile '{prof_name}' initial state '{initial}' is not in states.", rel, "Include initial in states."))
            if not isinstance(terminal, list) or not set(terminal).issubset(state_set):
                findings.append(_err("GOV-STATUS-GRAPH", f"Profile '{prof_name}' terminal states must be a subset of states.", rel, "Align terminal with states."))
                continue
            if not isinstance(transitions, dict):
                findings.append(_err("GOV-STATUS-GRAPH", f"Profile '{prof_name}' transitions must be an object.", rel, "Map each state to allowed target states."))
                continue
            for src, targets in transitions.items():
                if src not in state_set or not isinstance(targets, list) or not set(targets).issubset(state_set):
                    findings.append(_err(
                        "GOV-STATUS-GRAPH",
                        f"Profile '{prof_name}' transition from '{src}' references undeclared state.",
                        rel, "Ensure all transition sources and targets belong to states.",
                    ))
                elif src in set(terminal) and len(targets) > 0:
                    findings.append(_err(
                        "GOV-STATUS-GRAPH",
                        f"Terminal state '{src}' in profile '{prof_name}' ({rel}) must not declare outgoing transitions.",
                        rel, "Set terminal state outgoing transitions to [].",
                    ))
    return findings


def check_performance(root: Path) -> List[Finding]:
    """Validate wellmanifest/performance declarative budget and regression gate contracts."""
    candidates = _discover_candidates(root, (
        ".governance/performance-budget.json",
        "performance-budget.json",
        ".benchmarks/**/budget.json",
        "benchmarks/**/budget.json",
    ))
    if not candidates:
        return [_err(
            "GOV-PERFORMANCE-MISSING",
            "Repository requires wellmanifest/performance but no performance-budget.json was found.",
            ".governance/performance-budget.json",
            "Provide .governance/performance-budget.json with positive latency/throughput/regression budgets.",
        )]

    findings: List[Finding] = []
    threshold_keys = ("maxLatencyMs", "minThroughput", "maxMemoryBytes", "maxRegressionPct", "limit")
    for path in candidates:
        rel = _rel(root, path)
        doc, load_err = _load_unique_json(
            root, path, "GOV-PERFORMANCE-INVALID",
            "Provide a valid performance-budget JSON object.",
        )
        if load_err is not None or doc is None:
            findings.append(load_err)  # type: ignore[arg-type]
            continue
        if doc.get("schema") not in {"wellmanifest.performance-budget/v1", "wellmanifest.performance/v1"}:
            findings.append(_err(
                "GOV-PERFORMANCE-INVALID",
                f"{rel} must declare schema 'wellmanifest.performance-budget/v1' or 'wellmanifest.performance/v1'.",
                rel, "Set canonical performance budget schema.",
            ))
        budgets = doc.get("budgets") or doc.get("metrics")
        if not isinstance(budgets, list) or not budgets:
            findings.append(_err(
                "GOV-PERFORMANCE-INVALID",
                f"{rel} must declare a non-empty 'budgets' or 'metrics' array.",
                rel, "Define at least one measurable performance budget entry.",
            ))
            continue
        for idx, item in enumerate(budgets):
            if not isinstance(item, dict) or not isinstance(item.get("name") or item.get("id"), str):
                findings.append(_err("GOV-PERFORMANCE-BUDGET", f"Budget #{idx} in {rel} must declare string name/id.", rel, "Add metric name/id and positive threshold."))
                continue
            present = [item[k] for k in threshold_keys if k in item]
            if not present or any(type(v) not in (int, float) or v <= 0 for v in present):
                findings.append(_err(
                    "GOV-PERFORMANCE-BUDGET",
                    f"Budget '{item.get('name') or item.get('id')}' in {rel} must specify a positive numeric threshold ({', '.join(threshold_keys)}).",
                    rel, "Set a positive numeric threshold for every performance budget.",
                ))
    return findings


def check_llm(root: Path) -> List[Finding]:
    """Validate wellmanifest/llm policy boundary and credential-free profile contracts."""
    candidates = _discover_candidates(root, (
        ".wellmanifest/llm.json",
        ".governance/llm.json",
        "llm.json",
        "models/*.v1.json",
    ))
    if not candidates:
        return [_err(
            "GOV-LLM-MISSING",
            "Repository requires wellmanifest/llm but no .wellmanifest/llm.json or .governance/llm.json profile was found.",
            ".wellmanifest/llm.json",
            "Provide .wellmanifest/llm.json conforming to wellmanifest.llm-profile/v1.",
        )]

    findings: List[Finding] = []
    for path in candidates:
        rel = _rel(root, path)
        raw_text, raw_err = _read_bounded_text(root, path)
        if raw_err is None and raw_text is not None and _SECRET_MATERIAL_RE.search(raw_text):
            findings.append(_err(
                "GOV-LLM-SECRET",
                f"{rel} contains runtime provider credential material forbidden by wellmanifest/llm.",
                rel, "Remove provider credentials from LLM policy profiles.",
            ))
        doc, load_err = _load_unique_json(
            root, path, "GOV-LLM-INVALID",
            "Provide a valid wellmanifest.llm-profile/v1 JSON object.",
        )
        if load_err is not None or doc is None:
            findings.append(load_err)  # type: ignore[arg-type]
            continue
        if doc.get("schema") != "wellmanifest.llm-profile/v1":
            findings.append(_err(
                "GOV-LLM-INVALID",
                f"{rel} must declare schema 'wellmanifest.llm-profile/v1'.",
                rel, "Set schema to 'wellmanifest.llm-profile/v1'.",
            ))
        if not isinstance(doc.get("profileId"), str) or not doc["profileId"].strip():
            findings.append(_err("GOV-LLM-INVALID", f"{rel} must declare non-empty 'profileId'.", rel, "Set profileId."))
        if not isinstance(doc.get("version"), str) or not _SEMVER_RE.fullmatch(doc["version"]):
            findings.append(_err("GOV-LLM-INVALID", f"{rel} must declare semver 'version'.", rel, "Set semver version (e.g. 1.0.0)."))
        transport = doc.get("transport")
        if not isinstance(transport, dict) or transport.get("preferred") not in {"mcp", "https", "cli", "file"}:
            findings.append(_err(
                "GOV-LLM-INVALID",
                f"{rel} must declare transport.preferred in {{mcp, https, cli, file}}.",
                rel, "Configure canonical transport.preferred.",
            ))
        workflow = doc.get("workflow")
        if isinstance(workflow, list):
            for step in workflow:
                if not isinstance(step, dict) or step.get("operation") not in _LLM_CANONICAL_OPS:
                    findings.append(_err(
                        "GOV-LLM-OPERATION",
                        f"Workflow step in {rel} uses non-canonical operation '{step.get('operation') if isinstance(step, dict) else step}'.",
                        rel, f"Use canonical wellmanifest/llm operations: {', '.join(sorted(_LLM_CANONICAL_OPS))}.",
                    ))
    return findings


def check_dsl(root: Path) -> List[Finding]:
    """Validate wellmanifest/dsl interoperability manifests."""
    candidates = _discover_candidates(root, (
        "dsl-manifest.json",
        ".governance/dsl-manifest.json",
        "profiles/*dsl*.json",
    ))
    if not candidates:
        return [_err(
            "GOV-DSL-MISSING",
            "Repository requires wellmanifest/dsl but no dsl-manifest.json was found.",
            "dsl-manifest.json",
            "Provide dsl-manifest.json conforming to wellmanifest.dsl/manifest/v1.",
        )]

    findings: List[Finding] = []
    for path in candidates:
        rel = _rel(root, path)
        doc, load_err = _load_unique_json(
            root, path, "GOV-DSL-INVALID",
            "Provide a valid wellmanifest.dsl/manifest/v1 JSON object.",
        )
        if load_err is not None or doc is None:
            findings.append(load_err)  # type: ignore[arg-type]
            continue
        if doc.get("schema") != "wellmanifest.dsl/manifest/v1":
            findings.append(_err("GOV-DSL-INVALID", f"{rel} must declare schema 'wellmanifest.dsl/manifest/v1'.", rel, "Set schema to 'wellmanifest.dsl/manifest/v1'."))
        if not isinstance(doc.get("id"), str) or not _STABLE_ID_RE.fullmatch(doc["id"]):
            findings.append(_err("GOV-DSL-INVALID", f"{rel} must declare a valid stable 'id'.", rel, "Set canonical DSL id."))
        if not isinstance(doc.get("version"), str) or not _SEMVER_RE.fullmatch(doc["version"]):
            findings.append(_err("GOV-DSL-INVALID", f"{rel} must declare semver 'version'.", rel, "Set semver version."))
        for req_key in ("name", "domain"):
            if not isinstance(doc.get(req_key), str) or not doc[req_key].strip():
                findings.append(_err("GOV-DSL-INVALID", f"{rel} is missing non-empty '{req_key}'.", rel, f"Declare '{req_key}' in {rel}."))
    return findings


def check_env_dsl(root: Path) -> List[Finding]:
    """Validate wellmanifest/env-dsl environment variable contracts and secret separation."""
    candidates = _discover_candidates(root, (
        "env-dsl.json",
        ".governance/env-dsl.json",
        "env.contract.json",
        ".env.contract.json",
    ))
    if not candidates:
        return [_err(
            "GOV-ENV-DSL-MISSING",
            "Repository requires wellmanifest/env-dsl but no env-dsl.json or env.contract.json was found.",
            "env-dsl.json",
            "Provide env-dsl.json declaring environment variables and explicit secret separation.",
        )]

    findings: List[Finding] = []
    for path in candidates:
        rel = _rel(root, path)
        doc, load_err = _load_unique_json(
            root, path, "GOV-ENV-DSL-INVALID",
            "Provide a valid env-dsl JSON contract.",
        )
        if load_err is not None or doc is None:
            findings.append(load_err)  # type: ignore[arg-type]
            continue
        if doc.get("schema") not in {"wellmanifest.env-dsl/v1", "wellmanifest.env/contract/v1"}:
            findings.append(_err("GOV-ENV-DSL-INVALID", f"{rel} must declare schema 'wellmanifest.env-dsl/v1'.", rel, "Set schema to 'wellmanifest.env-dsl/v1'."))
        variables = doc.get("variables")
        if not isinstance(variables, dict) or not variables:
            findings.append(_err("GOV-ENV-DSL-INVALID", f"{rel} must declare a non-empty 'variables' object.", rel, "Map uppercase ENV_VAR names to their contract metadata."))
            continue
        for var_name, spec in variables.items():
            if not _ENV_VAR_RE.fullmatch(str(var_name)) or not isinstance(spec, dict):
                findings.append(_err("GOV-ENV-DSL-VARIABLE", f"Variable '{var_name}' in {rel} must use UPPER_SNAKE_CASE and an object spec.", rel, "Rename variable to UPPER_SNAKE_CASE."))
                continue
            if not isinstance(spec.get("secret"), bool):
                findings.append(_err(
                    "GOV-ENV-DSL-SECRET-SEPARATION",
                    f"Variable '{var_name}' in {rel} must explicitly declare boolean 'secret' for secret/env separation.",
                    rel, "Set 'secret': true or false on every environment variable.",
                ))
            elif spec["secret"] is True and spec.get("default") not in (None, ""):
                findings.append(_err(
                    "GOV-ENV-DSL-SECRET-DEFAULT",
                    f"Secret variable '{var_name}' in {rel} must not define a plaintext default value.",
                    rel, "Remove plaintext defaults from secret variables.",
                ))
    return findings


def check_code_dsl(root: Path) -> List[Finding]:
    """Validate wellmanifest/code-dsl semantic projections and stable non-file URIs."""
    candidates = _discover_candidates(root, (
        "code-dsl.json",
        ".governance/code-dsl.json",
        "projections/*code-dsl*.json",
    ))
    if not candidates:
        return [_err(
            "GOV-CODE-DSL-MISSING",
            "Repository requires wellmanifest/code-dsl but no code-dsl.json projection was found.",
            ".governance/code-dsl.json",
            "Provide .governance/code-dsl.json conforming to wellmanifest.code/json/v1.",
        )]

    findings: List[Finding] = []
    for path in candidates:
        rel = _rel(root, path)
        doc, load_err = _load_unique_json(
            root, path, "GOV-CODE-DSL-INVALID",
            "Provide a valid wellmanifest.code/json/v1 JSON object.",
        )
        if load_err is not None or doc is None:
            findings.append(load_err)  # type: ignore[arg-type]
            continue
        if doc.get("schema") != "wellmanifest.code/json/v1":
            findings.append(_err("GOV-CODE-DSL-INVALID", f"{rel} must declare schema 'wellmanifest.code/json/v1'.", rel, "Set schema to 'wellmanifest.code/json/v1'."))
        documents = doc.get("documents")
        if not isinstance(documents, list) or not documents:
            findings.append(_err("GOV-CODE-DSL-INVALID", f"{rel} must declare a non-empty 'documents' array.", rel, "Include workspace, query, or snapshot documents."))
            continue
        for idx, item in enumerate(documents):
            if not isinstance(item, dict) or item.get("kind") not in {"workspace", "query", "snapshot"}:
                findings.append(_err("GOV-CODE-DSL-INVALID", f"Document #{idx} in {rel} must declare kind in {{workspace, query, snapshot}}.", rel, "Set canonical document kind."))
                continue
            uri = str(item.get("uri", ""))
            if uri.lower().startswith("file:"):
                findings.append(_err(
                    "GOV-CODE-DSL-FILE-URI",
                    f"Document #{idx} in {rel} uses host-local '{uri}' URI; stable non-file URIs are required.",
                    rel, "Replace file:// URIs with repository-portable stable URIs.",
                ))
    return findings


def check_nl_dsl_llm(root: Path) -> List[Finding]:
    """Validate wellmanifest/nl-dsl-llm tripartite NL-DSL-LLM and MCP/CLI parity contracts."""
    candidates = _discover_candidates(root, (
        ".governance/nl-dsl-llm.json",
        "nl-dsl-llm.json",
        "contracts/nl-dsl-llm.json",
    ))
    if not candidates:
        return [_err(
            "GOV-NL-DSL-LLM-MISSING",
            "Repository requires wellmanifest/nl-dsl-llm but no nl-dsl-llm contract was found.",
            ".governance/nl-dsl-llm.json",
            "Provide .governance/nl-dsl-llm.json declaring tripartite NL/DSL/LLM bindings and MCP/CLI parity.",
        )]

    findings: List[Finding] = []
    for path in candidates:
        rel = _rel(root, path)
        doc, load_err = _load_unique_json(
            root, path, "GOV-NL-DSL-LLM-INVALID",
            "Provide a valid wellmanifest.nl-dsl-llm/v1 JSON contract.",
        )
        if load_err is not None or doc is None:
            findings.append(load_err)  # type: ignore[arg-type]
            continue
        if doc.get("schema") != "wellmanifest.nl-dsl-llm/v1":
            findings.append(_err("GOV-NL-DSL-LLM-INVALID", f"{rel} must declare schema 'wellmanifest.nl-dsl-llm/v1'.", rel, "Set schema to 'wellmanifest.nl-dsl-llm/v1'."))
        for layer in ("nl", "dsl", "llm"):
            if not isinstance(doc.get(layer), dict) or not doc[layer]:
                findings.append(_err("GOV-NL-DSL-LLM-INVALID", f"{rel} is missing non-empty '{layer}' layer contract.", rel, "Declare nl, dsl, and llm tripartite sections."))
        transports = doc.get("transports")
        if not isinstance(transports, list) or not {"mcp", "cli"}.issubset(set(transports)):
            findings.append(_err(
                "GOV-NL-DSL-LLM-PARITY",
                f"{rel} must declare universal MCP/CLI parity ('mcp' and 'cli' in transports).",
                rel, "Include both 'mcp' and 'cli' in transports.",
            ))
    return findings


def check_nl_api_llm(root: Path) -> List[Finding]:
    """Validate wellmanifest/nl-api-llm universal multi-protocol API registries."""
    candidates = _discover_candidates(root, (
        "api-registry.json",
        ".governance/api-registry.json",
        ".governance/nl-api-llm.json",
        "nl-api-llm.json",
    ))
    if not candidates:
        return [_err(
            "GOV-NL-API-LLM-MISSING",
            "Repository requires wellmanifest/nl-api-llm but no api-registry.json was found.",
            "api-registry.json",
            "Provide api-registry.json conforming to wellmanifest.api-registry/v1.",
        )]

    findings: List[Finding] = []
    for path in candidates:
        rel = _rel(root, path)
        doc, load_err = _load_unique_json(
            root, path, "GOV-NL-API-LLM-INVALID",
            "Provide a valid wellmanifest.api-registry/v1 JSON object.",
        )
        if load_err is not None or doc is None:
            findings.append(load_err)  # type: ignore[arg-type]
            continue
        if doc.get("schema") != "wellmanifest.api-registry/v1":
            findings.append(_err("GOV-NL-API-LLM-INVALID", f"{rel} must declare schema 'wellmanifest.api-registry/v1'.", rel, "Set schema to 'wellmanifest.api-registry/v1'."))
        if not isinstance(doc.get("version"), str) or not _SEMVER_RE.fullmatch(doc["version"]):
            findings.append(_err("GOV-NL-API-LLM-INVALID", f"{rel} must declare semver 'version'.", rel, "Set semver version."))
        services = doc.get("services")
        endpoints = doc.get("endpoints")
        if not isinstance(services, list) or not services:
            findings.append(_err("GOV-NL-API-LLM-INVALID", f"{rel} must declare a non-empty 'services' array.", rel, "Declare at least one API service."))
            continue
        service_ids: set[str] = set()
        for svc in services:
            if not isinstance(svc, dict) or not isinstance(svc.get("id"), str) or not svc["id"].strip() or svc.get("protocol") not in _API_PROTOCOLS:
                findings.append(_err("GOV-NL-API-LLM-SERVICE", f"Service entry in {rel} must declare non-empty id and supported protocol.", rel, "Set service id, name, and supported protocol."))
            else:
                service_ids.add(svc["id"])
        if not isinstance(endpoints, list) or not endpoints:
            findings.append(_err("GOV-NL-API-LLM-INVALID", f"{rel} must declare a non-empty 'endpoints' array.", rel, "Declare API endpoints referencing services."))
            continue
        for ep in endpoints:
            svc_ref = ep.get("serviceId") or ep.get("service") if isinstance(ep, dict) else None
            if not isinstance(ep, dict) or not isinstance(ep.get("id"), str) or svc_ref not in service_ids:
                findings.append(_err(
                    "GOV-NL-API-LLM-ENDPOINT",
                    f"Endpoint in {rel} must declare id and reference a declared serviceId.",
                    rel, "Ensure every endpoint binds to a declared service id.",
                ))
    return findings


def check_poa(root: Path) -> List[Finding]:
    """Validate wellmanifest/poa deterministic plan-of-action process contracts."""
    candidates = _discover_candidates(root, (
        "standard/poa-process.json",
        ".governance/poa.json",
        "poa-process.json",
        "poa.json",
    ))
    if not candidates:
        return [_err(
            "GOV-POA-MISSING",
            "Repository requires wellmanifest/poa but no poa-process.json or .governance/poa.json was found.",
            ".governance/poa.json",
            "Provide poa-process.json with acyclic deterministic action steps.",
        )]

    findings: List[Finding] = []
    for path in candidates:
        rel = _rel(root, path)
        doc, load_err = _load_unique_json(
            root, path, "GOV-POA-INVALID",
            "Provide a valid POA process JSON object.",
        )
        if load_err is not None or doc is None:
            findings.append(load_err)  # type: ignore[arg-type]
            continue
        if doc.get("schema") not in {"poa.process/v1", "wellmanifest.poa/v1"}:
            findings.append(_err("GOV-POA-INVALID", f"{rel} must declare schema 'poa.process/v1' or 'wellmanifest.poa/v1'.", rel, "Set canonical POA schema."))
        proc_id = doc.get("process_id") or doc.get("id")
        if not isinstance(proc_id, str) or not proc_id.strip():
            findings.append(_err("GOV-POA-INVALID", f"{rel} must declare non-empty 'process_id' or 'id'.", rel, "Set process_id."))
        steps = doc.get("steps")
        if not isinstance(steps, list) or not steps:
            findings.append(_err("GOV-POA-INVALID", f"{rel} must declare a non-empty 'steps' array.", rel, "Define deterministic POA steps."))
            continue
        deps_map: Dict[str, List[str]] = {}
        for idx, step in enumerate(steps):
            if not isinstance(step, dict) or not isinstance(step.get("id"), str) or not step["id"].strip():
                findings.append(_err("GOV-POA-STEP", f"Step #{idx} in {rel} must declare a non-empty string 'id'.", rel, "Assign unique step IDs."))
                continue
            sid = step["id"]
            if sid in deps_map:
                findings.append(_err("GOV-POA-STEP", f"Duplicate step id '{sid}' in {rel}.", rel, "Ensure unique step IDs."))
                continue
            if not isinstance(step.get("action") or step.get("operation"), str):
                findings.append(_err("GOV-POA-STEP", f"Step '{sid}' in {rel} must declare 'action' or 'operation'.", rel, "Bind step action/operation."))
            raw_deps = step.get("depends_on", [])
            if not isinstance(raw_deps, list) or not all(isinstance(d, str) for d in raw_deps):
                findings.append(_err("GOV-POA-DAG", f"Step '{sid}' depends_on in {rel} must be a list of step IDs.", rel, "List upstream step IDs."))
                deps_map[sid] = []
            else:
                deps_map[sid] = list(raw_deps)

        for sid, deps in deps_map.items():
            for dep in deps:
                if dep not in deps_map:
                    findings.append(_err("GOV-POA-DAG", f"Step '{sid}' in {rel} depends on unknown step '{dep}'.", rel, "Reference declared step IDs."))

        visiting: set[str] = set()
        visited: set[str] = set()

        def _has_cycle(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            for nxt in deps_map.get(node, ()):
                if nxt in deps_map and _has_cycle(nxt):
                    return True
            visiting.remove(node)
            visited.add(node)
            return False

        if any(_has_cycle(n) for n in deps_map):
            findings.append(_err("GOV-POA-DAG", f"POA step dependency graph in {rel} contains a cycle.", rel, "Break dependency cycles in POA steps."))
    return findings


def check_anonym(root: Path) -> List[Finding]:
    """Validate wellmanifest/anonym context-preserving anonymization envelopes and policies."""
    candidates = _discover_candidates(root, (
        ".governance/anonym.json",
        "anonym.json",
        "anonymization-envelope.json",
    ))
    if not candidates:
        return [_err(
            "GOV-ANONYM-MISSING",
            "Repository requires wellmanifest/anonym but no anonym.json or anonymization-envelope.json was found.",
            ".governance/anonym.json",
            "Provide .governance/anonym.json or anonymization-envelope.json conforming to wellmanifest.anonym/v1.",
        )]

    alias_key_re = re.compile(r"^[A-Z][A-Z0-9-]*$")
    findings: List[Finding] = []
    for path in candidates:
        rel = _rel(root, path)
        doc, load_err = _load_unique_json(
            root, path, "GOV-ANONYM-INVALID",
            "Provide a valid wellmanifest.anonym/v1 JSON object.",
        )
        if load_err is not None or doc is None:
            findings.append(load_err)  # type: ignore[arg-type]
            continue
        if doc.get("schema") != "wellmanifest.anonym/v1":
            findings.append(_err("GOV-ANONYM-INVALID", f"{rel} must declare schema 'wellmanifest.anonym/v1'.", rel, "Set schema to 'wellmanifest.anonym/v1'."))
        if doc.get("policy") != "context-preserving-v1":
            findings.append(_err("GOV-ANONYM-POLICY", f"{rel} must declare policy 'context-preserving-v1'.", rel, "Set policy to 'context-preserving-v1'."))
        mapping_id = doc.get("mappingId")
        if not isinstance(mapping_id, str) or not _STABLE_ID_RE.fullmatch(mapping_id):
            findings.append(_err("GOV-ANONYM-INVALID", f"{rel} must declare a valid 'mappingId'.", rel, "Set non-empty mappingId."))
        payload = doc.get("payload")
        payload_sha = doc.get("payloadSha256")
        if isinstance(payload, str):
            expected_sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            if not isinstance(payload_sha, str) or not _SHA256_HEX_RE.fullmatch(payload_sha) or payload_sha != expected_sha:
                findings.append(_err(
                    "GOV-ANONYM-DIGEST",
                    f"{rel} payloadSha256 does not match the UTF-8 SHA-256 digest of payload.",
                    rel, "Recompute payloadSha256 over the anonymized payload string.",
                ))
        alias_counts = doc.get("aliasCounts")
        if not isinstance(alias_counts, dict):
            findings.append(_err("GOV-ANONYM-INVALID", f"{rel} must declare an 'aliasCounts' object.", rel, "Provide aliasCounts mapping category prefixes to counts."))
        else:
            for k, v in alias_counts.items():
                if not alias_key_re.fullmatch(str(k)) or type(v) is not int or v < 1:
                    findings.append(_err(
                        "GOV-ANONYM-ALIAS",
                        f"Invalid aliasCounts entry '{k}: {v}' in {rel}.",
                        rel, "Use uppercase alias prefixes (e.g. PERSON, EMAIL) mapped to positive integer counts.",
                    ))
    return findings
