"""Deterministic S1 static conformance checkers for nohardcode, semver, and ssot."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from wellman.validator import Finding

SEMVER_RE = re.compile(
    r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*)?"
    r"(?:\+[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*)?$"
)
HEX40_RE = re.compile(r"^[a-f0-9]{40}$")
HEX64_RE = re.compile(r"^[a-f0-9]{64}$")
SHA256_PREF_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
SAFE_REL_PATH_RE = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))(?!.*\\).+$")
WAIVER_PATH_RE = re.compile(r"^(?!/)(?!(.*/)?\.\.(/|$))[^*?\[\\]+$")
NOHARDCODE_RULE_RE = re.compile(r"^NOHARDCODE-\d{3}$")
SEMVER_RULE_RE = re.compile(r"^SEMVER-\d{3}$")
SSOT_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")

NOHARDCODE_ENGINES: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "llm": {"provider": ("subllm", "ollama", "direct", "none")},
    "vision_yolo": {},
    "ocr_tesseract": {},
    "rule_engine_jev": {},
    "secrets_vault": {},
    "env_dsl": {},
    "adaptive_budget": {"strategy": ("ewma_latency", "exponential_jitter", "circuit_breaker", "dynamic_token_budget")},
    "schema_extractor": {},
    "model_router": {"routing_tier": ("capability", "cost_latency", "offline_first")},
    "dag_planner": {},
    "hardware_probe": {},
    "fuzzy_phonetic": {"algorithm": ("double_metaphone", "levenshtein", "embedding_cosine", "hybrid")},
    "adaptive_ranking": {"strategy": ("thompson_sampling", "ucb1", "decaying_feedback")},
}

SSOT_KINDS = frozenset({
    "generated_mirror", "vendored_copy", "facade", "allowed_divergence", "real_fork",
    "same_file_noise", "query_namespace", "served_artifact", "inventory_vs_runtime",
    "capability_surface", "locale_catalog", "config_binding", "pin_policy",
})
SSOT_ACTIONS = frozenset({
    "edit_upstream", "bump_pin", "keep_both_checkouts", "keep_facade_reexport_canonical",
    "add_parity_test", "keep_parity_test", "document_known_divergent", "vendor_and_gate_drift",
    "choose_canonical", "ask_clarifying_questions", "ignore_analyzer_until_interview",
    "scope_query_keys", "rebuild_served_artifact", "refuse_overwrite_dirty_tree",
    "do_not_count_discovery_as_connected", "test_operator_and_admin_separately",
    "use_locale_catalog", "bind_to_config_source", "declare_env_override",
})
SSOT_FORBIDS = frozenset({
    "delete_either_tree", "delete_generated_mirror", "treat_analyzer_as_debt",
    "couple_standalone_to_foreign_monorepo", "fork_logic_into_consumer",
    "leak_query_across_modules", "treat_source_as_served", "overwrite_dirty_working_tree",
    "count_lan_scan_as_connected_agent", "treat_visible_edit_as_authorized",
    "hardcode_ui_locale", "hardcode_deployment_value",
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


def validate_nohardcode_policies(root: Path) -> List[Finding]:
    """Validate wellmanifest/nohardcode policy descriptors and schema presence."""
    findings: List[Finding] = []
    candidates = _existing_files(root, (
        "nohardcode-policy.json", ".governance/nohardcode-policy.json", ".governance/nohardcode.json",
    ))
    for path in candidates:
        rel = _rel(root, path)
        try:
            doc = _unique_json_load(path)
        except Exception as exc:
            findings.append(_err("GOV-NOHARDCODE-POLICY-INVALID", f"Invalid NoHardcode policy JSON in {rel}: {exc}",
                                 rel, "Provide a valid JSON object without duplicate keys."))
            continue

        if doc.get("schema") != "wellmanifest.nohardcode/policy/v1":
            findings.append(_err("GOV-NOHARDCODE-POLICY-SCHEMA",
                                 f"{rel} must declare schema 'wellmanifest.nohardcode/policy/v1'.", rel,
                                 "Set schema to 'wellmanifest.nohardcode/policy/v1'."))
        if not SEMVER_RE.match(str(doc.get("version") or "")):
            findings.append(_err("GOV-NOHARDCODE-POLICY-VERSION", f"{rel} has invalid SemVer version.", rel,
                                 "Set version to a valid SemVer 2.0 string."))
        profile = doc.get("profile", "balanced")
        if profile not in {"strict", "balanced", "permissive"}:
            findings.append(_err("GOV-NOHARDCODE-POLICY-PROFILE", f"{rel} has unsupported profile '{profile}'.", rel,
                                 "Use 'strict', 'balanced', or 'permissive'."))

        engines = doc.get("engine_bindings")
        if not isinstance(engines, dict) or not engines:
            findings.append(_err("GOV-NOHARDCODE-ENGINE-INVALID", f"{rel} must define non-empty 'engine_bindings'.",
                                 rel, "Configure dynamic engine bindings per wellmanifest/nohardcode."))
        else:
            for eng_name, eng_cfg in engines.items():
                if eng_name not in NOHARDCODE_ENGINES or not isinstance(eng_cfg, dict) or not isinstance(eng_cfg.get("enabled"), bool):
                    findings.append(_err("GOV-NOHARDCODE-ENGINE-INVALID",
                                         f"{rel} engine binding '{eng_name}' is unknown or missing boolean 'enabled'.",
                                         rel, "Use canonical engine names and boolean 'enabled' flags."))
                    continue
                for enum_field, allowed_vals in NOHARDCODE_ENGINES[eng_name].items():
                    if enum_field in eng_cfg and eng_cfg[enum_field] not in allowed_vals:
                        findings.append(_err("GOV-NOHARDCODE-ENGINE-INVALID",
                                             f"{rel} engine '{eng_name}.{enum_field}' has unsupported value '{eng_cfg[enum_field]}'.",
                                             rel, f"Use one of: {', '.join(allowed_vals)}."))

        rules = doc.get("rules")
        if not isinstance(rules, dict) or not rules:
            findings.append(_err("GOV-NOHARDCODE-RULE-INVALID", f"{rel} must define non-empty 'rules'.", rel,
                                 "Configure NOHARDCODE-NNN rules with boolean 'enabled' and severity."))
        else:
            for rule_id, rule_cfg in rules.items():
                if (not NOHARDCODE_RULE_RE.match(str(rule_id))
                        or not isinstance(rule_cfg, dict)
                        or not isinstance(rule_cfg.get("enabled"), bool)
                        or rule_cfg.get("severity") not in {"error", "warning", "info"}):
                    findings.append(_err("GOV-NOHARDCODE-RULE-INVALID",
                                         f"{rel} rule '{rule_id}' must match NOHARDCODE-NNN with boolean 'enabled' and valid 'severity'.",
                                         rel, "Use NOHARDCODE-001..999 with enabled: true/false and severity: error|warning|info."))

        waivers = doc.get("waivers")
        if waivers is not None:
            if not isinstance(waivers, list):
                findings.append(_err("GOV-NOHARDCODE-WAIVER-INVALID", f"{rel} 'waivers' must be an array.", rel,
                                     "Declare waivers as a list of {path, rule, reason} objects."))
            else:
                for idx, waiver in enumerate(waivers):
                    if (not isinstance(waiver, dict)
                            or not WAIVER_PATH_RE.match(str(waiver.get("path") or ""))
                            or not NOHARDCODE_RULE_RE.match(str(waiver.get("rule") or ""))
                            or not str(waiver.get("reason") or "").strip()):
                        findings.append(_err("GOV-NOHARDCODE-WAIVER-INVALID",
                                             f"{rel} waivers[{idx}] must have concrete relative path (no wildcards/traversal), NOHARDCODE-NNN rule, and non-blank reason.",
                                             rel, "Replace wildcard or traversal waiver paths with exact relative file paths and a non-blank reason."))
    return findings


def _validate_semver_document(doc: Dict[str, Any], rel: str) -> List[Finding]:
    findings: List[Finding] = []
    schema = doc.get("schema")
    if schema == "wellmanifest.semver/policy/v1":
        if doc.get("authority") != "none" or doc.get("effect_model") != "read-only-conformance":
            findings.append(_err("SEMVER-POLICY-001",
                                 f"{rel} must preserve authority='none' and effect_model='read-only-conformance'.",
                                 rel, "SemVer conformance contracts must never claim deployment or flashing authority."))
        rules = doc.get("rules")
        if not isinstance(rules, list) or not rules or not all(
            isinstance(r, dict) and SEMVER_RULE_RE.match(str(r.get("id") or "")) for r in rules
        ):
            findings.append(_err("SEMVER-POLICY-001", f"{rel} must define non-empty SEMVER-NNN rules.", rel,
                                 "Populate 'rules' with canonical SEMVER-NNN rule definitions."))
    elif schema == "wellmanifest.semver/embedded-release/v1":
        if not SEMVER_RE.match(str(doc.get("system_version") or "")):
            findings.append(_err("SEMVER-001", f"{rel} has invalid system_version SemVer.", rel,
                                 "Use valid SemVer 2.0 for system_version."))
        comps = doc.get("components")
        if not isinstance(comps, list) or not comps:
            findings.append(_err("SEMVER-001", f"{rel} must declare a non-empty 'components' array.", rel,
                                 "Declare host, firmware, or contract components."))
        else:
            for comp in comps:
                if not isinstance(comp, dict):
                    findings.append(_err("SEMVER-001", f"{rel} component entry must be an object.", rel, "Fix component object."))
                    continue
                cid = str(comp.get("component_id") or "unknown")
                if not SEMVER_RE.match(str(comp.get("version") or "")):
                    findings.append(_err("SEMVER-001", f"{rel} component '{cid}' has invalid SemVer.", rel,
                                         "Use valid SemVer 2.0 for component version."))
                if not HEX40_RE.match(str(comp.get("git_commit") or "")):
                    findings.append(_err("SEMVER-002", f"{rel} component '{cid}' has invalid 40-hex git_commit.", rel,
                                         "Bind every component to an immutable 40-char git commit SHA."))
                if comp.get("tier") == "microcontroller_firmware":
                    if not str(comp.get("target_hardware") or "").strip():
                        findings.append(_err("SEMVER-004", f"{rel} MCU component '{cid}' missing target_hardware.", rel,
                                             "Declare target_hardware board/SoC constraint."))
                    bin_id = comp.get("binary_identity")
                    if (not isinstance(bin_id, dict)
                            or not HEX64_RE.match(str(bin_id.get("sha256") or ""))
                            or not HEX64_RE.match(str(bin_id.get("elf_sha256") or ""))):
                        findings.append(_err("SEMVER-002", f"{rel} MCU component '{cid}' requires 64-hex binary sha256 and elf_sha256.",
                                             rel, "Bind MCU releases to both binary sha256 and ELF sha256 digests."))
                    elif bin_id.get("target_partition") not in {"ota_0", "ota_1", "app_dual"}:
                        findings.append(_err("SEMVER-013", f"{rel} MCU component '{cid}' must use A/B dual-bank partition.",
                                             rel, "Set target_partition to 'ota_0', 'ota_1', or 'app_dual'."))
        compat = doc.get("compatibility")
        if not isinstance(compat, dict) or not str(compat.get("oql_contract_version") or "").strip():
            findings.append(_err("SEMVER-003", f"{rel} missing compatibility.oql_contract_version.", rel,
                                 "Declare compatibility.oql_contract_version."))
        att = doc.get("pipeline_attestation")
        if not isinstance(att, dict) or not all(
            att.get(flag) is True for flag in ("dual_build_verified", "hil_simulation_passed", "safe_state_preconditions_verified")
        ):
            findings.append(_err("SEMVER-012",
                                 f"{rel} pipeline_attestation must confirm dual_build_verified, hil_simulation_passed, and safe_state_preconditions_verified.",
                                 rel, "Verify dual-build, HIL simulation, and safe-state preconditions before release."))
    elif schema == "wellmanifest.semver/pipeline-run/v1":
        if not HEX40_RE.match(str(doc.get("commit_sha") or "")):
            findings.append(_err("SEMVER-002", f"{rel} pipeline-run requires 40-hex commit_sha.", rel,
                                 "Set commit_sha to a 40-hex Git SHA."))
        verdict = doc.get("verdict")
        if verdict not in {"PASSED", "FAILED", "BLOCKED"}:
            findings.append(_err("SEMVER-009", f"{rel} pipeline-run has invalid verdict '{verdict}'.", rel,
                                 "Use PASSED, FAILED, or BLOCKED."))
        stages = doc.get("stages") if isinstance(doc.get("stages"), dict) else {}
        if verdict == "PASSED":
            dual = stages.get("dual_build") if isinstance(stages.get("dual_build"), dict) else {}
            if not (dual.get("passed") is True
                    and HEX64_RE.match(str(dual.get("host_container_sha256") or ""))
                    and HEX64_RE.match(str(dual.get("firmware_elf_sha256") or ""))):
                findings.append(_err("SEMVER-009", f"{rel} PASSED pipeline-run requires verified dual_build digests.",
                                     rel, "Provide 64-hex host_container_sha256 and firmware_elf_sha256."))
            safe = stages.get("safe_state_validation") if isinstance(stages.get("safe_state_validation"), dict) else {}
            if not all(safe.get(k) is True for k in ("passed", "motors_deenergized", "pumps_stopped", "valves_closed")):
                findings.append(_err("SEMVER-012", f"{rel} PASSED pipeline-run requires safe_state_validation preconditions.",
                                     rel, "Ensure motors_deenergized, pumps_stopped, and valves_closed are true."))
    elif schema == "wellmanifest.semver/hardware-matrix/v1":
        profiles = doc.get("profiles")
        if not str(doc.get("matrix_version") or "").strip() or not isinstance(profiles, list) or not profiles:
            findings.append(_err("SEMVER-004", f"{rel} hardware-matrix requires matrix_version and non-empty profiles.",
                                 rel, "Populate matrix_version and hardware profiles."))
        else:
            for idx, prof in enumerate(profiles):
                if not isinstance(prof, dict) or not all(
                    str(prof.get(k) or "").strip() for k in ("profile_id", "board_model", "soc", "supported_firmware_semver_range")
                ):
                    findings.append(_err("SEMVER-004", f"{rel} profiles[{idx}] missing board/SoC/semver range.", rel,
                                         "Declare profile_id, board_model, soc, and supported_firmware_semver_range."))
    else:
        findings.append(_err("GOV-SEMVER-SCHEMA-INVALID", f"{rel} declares unsupported SemVer schema '{schema}'.", rel,
                             "Use a canonical wellmanifest.semver/*/v1 schema."))
    return findings


def check_semver_pack(root: Path) -> List[Finding]:
    """Validate wellmanifest/semver version carriers and release/pipeline/matrix descriptors."""
    findings: List[Finding] = []
    version_files = ("VERSION", "pyproject.toml", "package.json", "Cargo.toml")
    has_carrier = any((root / vf).is_file() for vf in version_files)
    version_path = root / "VERSION"
    if version_path.is_file():
        raw_ver = version_path.read_text(encoding="utf-8", errors="replace").strip()
        if not SEMVER_RE.match(raw_ver):
            findings.append(_err("GOV-SEMVER-VERSION-INVALID", f"VERSION contains invalid SemVer '{raw_ver}'.",
                                 "VERSION", "Write a valid SemVer 2.0 string (e.g. 0.1.0) in VERSION."))

    candidates = _existing_files(root, (".governance/semver*.json", "semver*.json"))
    for optional in _existing_files(root, ("policy.json", "examples/*.json")):
        try:
            probe = _unique_json_load(optional)
        except Exception:
            continue
        if str(probe.get("schema") or "").startswith("wellmanifest.semver/") and optional not in candidates:
            candidates.append(optional)

    if not has_carrier and not candidates:
        return [_err(
            "GOV-SEMVER-MISSING",
            "Repository requires wellmanifest/semver but no version carrier or SemVer manifest was found.",
            "VERSION",
            "Add a VERSION file or SemVer release/policy manifest.",
        )]

    for path in candidates:
        rel = _rel(root, path)
        try:
            doc = _unique_json_load(path)
        except Exception as exc:
            findings.append(_err("GOV-SEMVER-INVALID", f"Invalid SemVer JSON in {rel}: {exc}", rel,
                                 "Ensure valid JSON object without duplicate keys."))
            continue
        findings.extend(_validate_semver_document(doc, rel))
    return findings


def _validate_ssot_document(doc: Dict[str, Any], rel: str) -> List[Finding]:
    findings: List[Finding] = []
    schema = doc.get("schema")
    if schema == "wellmanifest.ssot/decision/v1":
        if not SSOT_ID_RE.match(str(doc.get("id") or "")) or not SEMVER_RE.match(str(doc.get("version") or "")):
            findings.append(_err("GOV-SSOT-DECISION-INVALID", f"{rel} requires valid identifier 'id' and SemVer 'version'.",
                                 rel, "Set valid id and SemVer version."))
        ctx = doc.get("context")
        if (not isinstance(ctx, dict)
                or not SSOT_ID_RE.match(str(ctx.get("subject") or ""))
                or not isinstance(ctx.get("languages"), list) or not ctx.get("languages")
                or not isinstance(ctx.get("packaging"), list) or not ctx.get("packaging")
                or not isinstance(ctx.get("analyzer"), dict)):
            findings.append(_err("GOV-SSOT-DECISION-INVALID", f"{rel} missing valid 'context' block.", rel,
                                 "Declare subject, languages, packaging, and analyzer in context."))
        pol = doc.get("policy")
        if (not isinstance(pol, dict)
                or pol.get("kind") != "pin_policy"
                or pol.get("edit") not in {"upstream", "local-only"}
                or pol.get("onChange") not in {"bump_pin", "re_vendor", "none"}
                or not isinstance(pol.get("forbid"), list)
                or not all(item in SSOT_FORBIDS for item in pol.get("forbid", []))):
            findings.append(_err("GOV-SSOT-POLICY-INVALID", f"{rel} has invalid 'policy' pinPolicy contract.", rel,
                                 "Use kind='pin_policy' with canonical edit, onChange, and forbid values."))
        decisions = doc.get("decisions")
        if not isinstance(decisions, list) or not isinstance(doc.get("questions"), list):
            findings.append(_err("GOV-SSOT-DECISION-INVALID", f"{rel} requires 'decisions' and 'questions' arrays.", rel,
                                 "Declare 'decisions' and 'questions' arrays."))
        else:
            for idx, dec in enumerate(decisions):
                if (not isinstance(dec, dict)
                        or not SSOT_ID_RE.match(str(dec.get("id") or ""))
                        or dec.get("kind") not in SSOT_KINDS
                        or not str(dec.get("rationale") or "").strip()
                        or not isinstance(dec.get("trees"), list) or not dec.get("trees")
                        or not all(SAFE_REL_PATH_RE.match(str(t)) for t in dec.get("trees", []))):
                    findings.append(_err("SSOT-KIND-001",
                                         f"{rel} decisions[{idx}] must have valid id, canonical kind, safe relative trees, and non-empty rationale.",
                                         rel, "Provide canonical SSOT decision kind, relative trees without '..', and rationale."))
                    continue
                actions = dec.get("actions")
                if not isinstance(actions, list) or not actions or not all(
                    isinstance(a, dict) and a.get("do") in SSOT_ACTIONS for a in actions
                ):
                    findings.append(_err("SSOT-ACTION-001",
                                         f"{rel} decisions[{idx}] must use propose-only canonical actions.", rel,
                                         "Use only propose-only SSOT actions; never direct deletion or merge commands."))
    elif schema == "wellmanifest.standards-lock/v1":
        if not SEMVER_RE.match(str(doc.get("version") or "")):
            findings.append(_err("SSOT-PIN-001", f"{rel} standards-lock requires SemVer version.", rel, "Set valid SemVer version."))
        entries = doc.get("entries")
        if not isinstance(entries, list) or not entries:
            findings.append(_err("SSOT-PIN-001", f"{rel} standards-lock requires non-empty 'entries'.", rel,
                                 "Pin at least one upstream standard revision and contract digest."))
        else:
            for idx, entry in enumerate(entries):
                contracts = entry.get("contracts") if isinstance(entry, dict) else None
                if (not isinstance(entry, dict)
                        or not HEX40_RE.match(str(entry.get("revision") or ""))
                        or not isinstance(contracts, list) or not contracts
                        or not all(isinstance(c, dict) and SHA256_PREF_RE.match(str(c.get("digest") or "")) for c in contracts)):
                    findings.append(_err("SSOT-PIN-001",
                                         f"{rel} entries[{idx}] must pin a 40-hex revision and sha256:<64-hex> contract digests.",
                                         rel, "Pin exact 40-hex commit revisions and sha256 digests."))
        upd = doc.get("updatePolicy")
        if not isinstance(upd, dict) or upd.get("merge") != "trusted-validator":
            findings.append(_err("SSOT-POLICY-001", f"{rel} updatePolicy.merge must equal 'trusted-validator'.", rel,
                                 "Require 'trusted-validator' merge authority in updatePolicy."))
    elif schema in {"wellmanifest.ssot/interview/v1", "wellmanifest.project-ssot/v1"}:
        if not str(doc.get("id") or doc.get("project") or "").strip():
            findings.append(_err("GOV-SSOT-SCHEMA-INVALID", f"{rel} missing required subject identifier.", rel,
                                 "Declare non-empty 'id' or 'project'."))
    else:
        findings.append(_err("GOV-SSOT-SCHEMA-INVALID",
                             f"{rel} is missing a supported wellmanifest.ssot schema declaration.", rel,
                             "Declare 'wellmanifest.ssot/decision/v1', 'wellmanifest.ssot/interview/v1', or 'wellmanifest.standards-lock/v1'."))
    return findings


def check_ssot_pack(root: Path, *, require_present: bool = False) -> List[Finding]:
    """Validate wellmanifest/ssot decision, interview, and standards-lock documents."""
    candidates = _existing_files(root, (
        ".governance/ssot.json", "ssot.json", "*.ssot.json",
        ".governance/standards-lock.json", "standards-lock.json",
        ".governance/project-ssot.json", "project-ssot.json",
    ))
    for example in _existing_files(root, ("examples/*.ssot.json", "examples/standards-lock.adopter.json")):
        if example not in candidates:
            candidates.append(example)

    has_pack_schema = (root / "schemas" / "ssot-decision.schema.json").is_file() or (root / "schemas" / "project-ssot.schema.json").is_file()
    if not candidates:
        if require_present and not has_pack_schema:
            return [_err(
                "GOV-SSOT-MISSING",
                "Repository requires wellmanifest/ssot but no SSOT decision or standards-lock contract was found.",
                ".governance/ssot.json",
                "Provide .governance/ssot.json, *.ssot.json, or standards-lock.json per wellmanifest/ssot.",
            )]
        return []

    findings: List[Finding] = []
    for path in candidates:
        rel = _rel(root, path)
        try:
            doc = _unique_json_load(path)
        except Exception as exc:
            findings.append(_err("GOV-SSOT-SYNTAX-ERROR", f"{rel} contains invalid JSON: {exc}", rel,
                                 f"Fix JSON syntax and duplicate keys in {rel}."))
            continue
        findings.extend(_validate_ssot_document(doc, rel))
    return findings
