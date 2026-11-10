"""Deterministic S1 static conformance checkers for uriprocess, taskand, and nl-uri-dsl-llm."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple

from wellman.validator import Finding

SEMVER_RE = re.compile(
    r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*)?"
    r"(?:\+[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*)?$"
)
HEX40_RE = re.compile(r"^[a-f0-9]{40}$")
HEX64_RE = re.compile(r"^[a-f0-9]{64}$")
SAFE_REL_PATH_RE = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))(?!.*\\).+$")
URI_OPERATION_RE = re.compile(r"^[a-z][a-z0-9+.-]*://[^\s?#]+$")
UUID_URN_RE = re.compile(r"^urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
PROC_URN_RE = re.compile(r"^urn:[a-z0-9_-]+:proc:[a-zA-Z0-9._-]+$")
PROCESS_URI_RE = re.compile(r"^process://[a-zA-Z0-9._-]+/.*$")

URIPROCESS_SCHEMAS = frozenset({
    "uriprocess.package/v1",
    "uriprocess.native-package/v1",
    "uriprocess.rust-package/v1",
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

    if path.is_symlink():
        raise ValueError("refusing symlink document")
    raw = path.read_bytes()
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("document exceeds 2 MiB limit")
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=hook)
    if not isinstance(data, dict):
        raise ValueError("expected top-level JSON object")
    return data


def _existing_files(root: Path, patterns: Iterable[str]) -> List[Path]:
    found: List[Path] = []
    for pat in patterns:
        for candidate in sorted(root.glob(pat)):
            if ".worktrees" in candidate.relative_to(root).parts or ".venv" in candidate.relative_to(root).parts:
                continue
            if (candidate.is_file() or candidate.is_symlink()) and candidate not in found:
                found.append(candidate)
    return found


def _verify_bundle_files(root: Path, doc: Dict[str, Any], rel: str, prefix: str) -> List[Finding]:
    findings: List[Finding] = []
    if not SEMVER_RE.match(str(doc.get("version") or "")):
        findings.append(_err(f"{prefix}-VERSION", f"{rel} must declare a valid SemVer version.", rel,
                             "Set version to a valid SemVer 2.0 string."))
    files = doc.get("files")
    if not isinstance(files, dict) or not files:
        findings.append(_err(f"{prefix}-FILES", f"{rel} must declare a non-empty 'files' SHA-256 map.", rel,
                             "Declare relative file paths mapped to lowercase 64-hex SHA-256 digests."))
        return findings

    for entry_path, expected_hex in files.items():
        if not isinstance(entry_path, str) or not SAFE_REL_PATH_RE.match(entry_path):
            findings.append(_err(f"{prefix}-PATH", f"{rel} contains unsafe bundle path '{entry_path}'.", rel,
                                 "Use safe relative POSIX paths without '..' or leading '/'."))
            continue
        if not isinstance(expected_hex, str) or not HEX64_RE.match(expected_hex):
            findings.append(_err(f"{prefix}-DIGEST", f"{rel} entry '{entry_path}' has invalid SHA-256 digest.", rel,
                                 "Use lowercase 64-character hex SHA-256 digests."))
            continue
        target = root / entry_path
        if target.is_symlink() or not target.is_file():
            findings.append(_err(f"{prefix}-MISSING-FILE", f"{rel} declared file '{entry_path}' is missing or a symlink.",
                                 rel, "Ensure all bundled files exist as regular files."))
            continue
        actual_hex = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual_hex != expected_hex:
            findings.append(_err(f"{prefix}-MISMATCH",
                                 f"{rel} SHA-256 mismatch for '{entry_path}' (expected {expected_hex[:12]}…, got {actual_hex[:12]}…).",
                                 entry_path, "Regenerate bundle digests or restore the canonical file bytes."))
    return findings


def check_uriprocess_pack(root: Path) -> List[Finding]:
    """Validate wellmanifest/uriprocess standard bundles, package manifests, provenance, and uri() invocations."""
    from wellman.uri import uri, validate_process_uri

    findings: List[Finding] = []

    bundle_path = root / "bundle.json"
    if bundle_path.exists() or bundle_path.is_symlink():
        try:
            bdoc = _unique_json_load(bundle_path)
            if bdoc.get("schema") == "wellmanifest.uriprocess/bundle/v1":
                if bdoc.get("standard") != "wellmanifest/uriprocess":
                    findings.append(_err("URP-SCHEMA-001", "bundle.json standard must be 'wellmanifest/uriprocess'.",
                                         "bundle.json", "Set standard to 'wellmanifest/uriprocess'."))
                findings.extend(_verify_bundle_files(root, bdoc, "bundle.json", "URP-INTEGRITY"))
        except Exception as exc:
            findings.append(_err("URP-DATA-001", f"Invalid bundle.json: {exc}", "bundle.json",
                                 "Provide a valid duplicate-free JSON object."))

    policy_path = root / "policy.json"
    if policy_path.exists() or policy_path.is_symlink():
        try:
            pdoc = _unique_json_load(policy_path)
            if pdoc.get("schema") == "wellmanifest.uriprocess/policy/v1":
                if pdoc.get("execution_authority") is not False:
                    findings.append(_err("URP-SCHEMA-001", "uriprocess policy.json must set execution_authority to false.",
                                         "policy.json", "Set execution_authority: false."))
                if not SEMVER_RE.match(str(pdoc.get("version") or "")):
                    findings.append(_err("URP-SCHEMA-001", "uriprocess policy.json must declare a valid SemVer version.",
                                         "policy.json", "Set version to a valid SemVer 2.0 string."))
        except Exception as exc:
            findings.append(_err("URP-DATA-001", f"Invalid policy.json: {exc}", "policy.json",
                                 "Provide a valid duplicate-free JSON object."))

    pkg_manifest = root / "uriprocess.json"
    if pkg_manifest.exists() or pkg_manifest.is_symlink():
        if pkg_manifest.is_symlink():
            findings.append(_err("URP-PATH-001", "uriprocess.json must not be a symlink.", "uriprocess.json",
                                 "Replace symlink with a regular uriprocess.json manifest."))
        else:
            try:
                data = _unique_json_load(pkg_manifest)
            except Exception as exc:
                findings.append(_err("URP-DATA-001", f"Invalid uriprocess.json: {exc}", "uriprocess.json",
                                     "Ensure uriprocess.json is valid JSON without duplicate keys."))
            else:
                schema = data.get("schema")
                if schema is not None and schema not in URIPROCESS_SCHEMAS:
                    findings.append(_err("URP-SCHEMA-001", f"Unsupported uriprocess.json schema '{schema}'.",
                                         "uriprocess.json", f"Use one of {sorted(URIPROCESS_SCHEMAS)}."))
                uris: List[Any] = []
                pub_uris = data.get("public_uris")
                if pub_uris is not None:
                    if not isinstance(pub_uris, list) or len(pub_uris) != len(set(map(str, pub_uris))):
                        findings.append(_err("URP-IDENTITY-001", "public_uris must be an array of unique URI strings.",
                                             "uriprocess.json", "Provide unique canonical URIs in public_uris."))
                    else:
                        uris.extend(pub_uris)
                if "process_ref" in data:
                    uris.append(data["process_ref"])
                if not uris:
                    findings.append(_err("URP-SCHEMA-001", "uriprocess.json must declare 'public_uris' or 'process_ref'.",
                                         "uriprocess.json", "Declare canonical process URIs in uriprocess.json."))
                for u in uris:
                    try:
                        validate_process_uri(str(u))
                    except Exception as exc:
                        findings.append(_err("URP-IDENTITY-001", f"Invalid process URI '{u}' in uriprocess.json: {exc}",
                                             "uriprocess.json", "Use canonical 'scheme://authority/path' process URIs."))
                if schema == "uriprocess.rust-package/v1":
                    crate = data.get("crate")
                    transports = data.get("transports")
                    fallback = data.get("fallback_chain")
                    if not isinstance(crate, str) or not crate.strip():
                        findings.append(_err("URP-SCHEMA-001", "rust-uri-v1 requires non-empty 'crate' identity (URP-011).",
                                             "uriprocess.json", "Declare Cargo crate identity in 'crate'."))
                    if not isinstance(transports, list) or not set(transports).intersection({"cdylib", "json-stdin-stdout"}):
                        findings.append(_err("URP-SCHEMA-001",
                                             "rust-uri-v1 requires 'cdylib' or 'json-stdin-stdout' in 'transports' (URP-011).",
                                             "uriprocess.json", "Declare supported transports in uriprocess.json."))
                    if not isinstance(fallback, list) or len(fallback) < 1:
                        findings.append(_err("URP-SCHEMA-001", "rust-uri-v1 requires a non-empty 'fallback_chain' (URP-011).",
                                             "uriprocess.json", "Declare prioritized Python fallback chain."))

    prov_path = root / "provenance.json"
    if prov_path.exists() or prov_path.is_symlink():
        try:
            prov = _unique_json_load(prov_path)
            commit = prov.get("upstream_commit") or (prov.get("upstream", {}) if isinstance(prov.get("upstream"), dict) else {}).get("commit")
            if not isinstance(commit, str) or not HEX40_RE.match(commit):
                findings.append(_err("URP-IDENTITY-001", "provenance.json must record a 40-hex upstream Git commit.",
                                     "provenance.json", "Set upstream_commit to the exact 40-hex commit SHA."))
            tests = prov.get("tests")
            if not isinstance(tests, list) or not tests or not all(isinstance(t, str) and SAFE_REL_PATH_RE.match(t) for t in tests):
                findings.append(_err("URP-TESTS-001", "provenance.json must preserve a non-empty safe relative 'tests' list.",
                                     "provenance.json", "Include original relative test paths in provenance.json."))
        except Exception as exc:
            findings.append(_err("URP-DATA-001", f"Invalid provenance.json: {exc}", "provenance.json",
                                 "Ensure provenance.json is valid duplicate-free JSON."))

    scan_env = uri("proc://uriprocess/invocation/scan", {"root": str(root)})
    scan_res = scan_env.get("result", {})
    for item in scan_res.get("invalid_links", []):
        rel_item = str(item.get("path", ""))
        parts = Path(rel_item).parts
        msg = str(item.get("message", ""))
        if ("tests" in parts or "test" in parts or "fixtures" in parts
                or re.search(r"'[<\{][^'\"]+[>\}]'", msg)):
            continue
        findings.append(_err(
            item.get("code", "URP-IDENTITY-001"),
            f"{msg} at line {item.get('line')}",
            rel_item,
            "Use canonical 'scheme://authority/path' process URI in uri('...') invocations.",
        ))
    return findings


def _detect_dag_cycle(graph: Dict[str, List[str]]) -> List[str]:
    visited: Set[str] = set()
    active: Set[str] = set()

    def dfs(node: str) -> List[str]:
        if node in active:
            return [node]
        if node in visited:
            return []
        active.add(node)
        for dep in graph.get(node, []):
            cyc = dfs(dep)
            if cyc:
                return [node, *cyc]
        active.remove(node)
        visited.add(node)
        return []

    for key in sorted(graph):
        cyc = dfs(key)
        if cyc:
            return cyc
    return []


def check_taskand_pack(root: Path) -> List[Finding]:
    """Validate wellmanifest/taskand bundles, policies, capsules, grants, and DAG task definitions."""
    findings: List[Finding] = []

    bundle_path = root / "bundle.json"
    has_bundle = bundle_path.is_file() or bundle_path.is_symlink()
    if has_bundle:
        try:
            bdoc = _unique_json_load(bundle_path)
        except Exception as exc:
            findings.append(_err("GOV-TASKAND-BUNDLE-INVALID", f"Invalid taskand bundle.json: {exc}", "bundle.json",
                                 "Provide a valid duplicate-free JSON object for bundle.json."))
        else:
            if bdoc.get("schema") == "wellmanifest.taskand/bundle/v1":
                if bdoc.get("standard") != "wellmanifest/taskand":
                    findings.append(_err("GOV-TASKAND-BUNDLE-SCHEMA",
                                         "taskand bundle.json must declare standard 'wellmanifest/taskand'.",
                                         "bundle.json", "Set standard to 'wellmanifest/taskand'."))
                findings.extend(_verify_bundle_files(root, bdoc, "bundle.json", "GOV-TASKAND-BUNDLE"))

    policy_path = root / "policy.json"
    has_taskand_policy = False
    if policy_path.is_file() or policy_path.is_symlink():
        try:
            pdoc = _unique_json_load(policy_path)
            if pdoc.get("schema") == "wellmanifest.taskand/policy/v1":
                has_taskand_policy = True
                if not SEMVER_RE.match(str(pdoc.get("version") or "")):
                    findings.append(_err("GOV-TASKAND-POLICY-VERSION", "taskand policy.json has invalid SemVer version.",
                                         "policy.json", "Set version to a valid SemVer 2.0 string."))
                reqs = pdoc.get("requirements")
                if not isinstance(reqs, list) or not reqs:
                    findings.append(_err("GOV-TASKAND-POLICY-REQS", "taskand policy.json must declare non-empty requirements.",
                                         "policy.json", "Populate normative TKD-* requirements in policy.json."))
        except Exception as exc:
            findings.append(_err("GOV-TASKAND-POLICY-INVALID", f"Invalid policy.json: {exc}", "policy.json",
                                 "Provide a valid duplicate-free JSON object."))

    capsule_files = _existing_files(root, (
        "capsule.json", "grants.json", "proc-catalog.json", "conformance/taskand*.json", ".governance/taskand*.json",
    ))
    for path in capsule_files:
        rel = _rel(root, path)
        try:
            doc = _unique_json_load(path)
        except Exception as exc:
            findings.append(_err("GOV-TASKAND-DOC-INVALID", f"Invalid taskand JSON in {rel}: {exc}", rel,
                                 "Ensure taskand descriptor is valid JSON without duplicate keys."))
            continue

        schema = doc.get("schema")
        if schema == "taskand.capsule/v1":
            cap_id = doc.get("id") or doc.get("name")
            if not isinstance(cap_id, str) or not cap_id.strip():
                findings.append(_err("GOV-TASKAND-CAPSULE-ID", f"{rel} must declare a non-empty capsule id/name.", rel,
                                     "Set 'id' in capsule.json."))
        if "grants" in doc:
            grants = doc.get("grants")
            if not isinstance(grants, list):
                findings.append(_err("GOV-TASKAND-GRANTS-INVALID", f"{rel} 'grants' must be a list.", rel,
                                     "Declare explicit bounded capability grants as an array."))
            else:
                for idx, grant in enumerate(grants):
                    if not isinstance(grant, dict):
                        findings.append(_err("GOV-TASKAND-GRANTS-INVALID", f"{rel} grant[{idx}] must be an object.", rel,
                                             "Use structured grant objects."))
                        continue
                    eff = grant.get("effect") or grant.get("capability")
                    res = grant.get("resource") or grant.get("scope")
                    if eff == "*" or res == "*":
                        findings.append(_err("GOV-TASKAND-WILDCARD-GRANT",
                                             f"{rel} grant[{idx}] uses forbidden wildcard capability or scope.", rel,
                                             "Bind grants to explicit capability names and bounded scopes."))
        tasks = doc.get("tasks") or doc.get("steps")
        if isinstance(tasks, list):
            graph: Dict[str, List[str]] = {}
            for idx, task in enumerate(tasks):
                if isinstance(task, dict) and isinstance(task.get("id"), str):
                    deps = task.get("depends_on") or []
                    if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
                        findings.append(_err("GOV-TASKAND-DAG-INVALID",
                                             f"{rel} task '{task['id']}' depends_on must be a list of task IDs.", rel,
                                             "Specify string task IDs in depends_on."))
                    else:
                        graph[task["id"]] = list(deps)
            cyc = _detect_dag_cycle(graph)
            if cyc:
                findings.append(_err("GOV-TASKAND-DAG-CYCLE",
                                     f"{rel} contains cyclic task dependency: {' -> '.join(cyc)}.", rel,
                                     "Break dependency cycles so the task graph forms a valid DAG."))

    has_schemas = (root / "schemas" / "capsule.v1.json").is_file() or (root / "schemas" / "proc.v1.json").is_file()
    has_src_dag = (
        any(
            "depends_on" in p.read_text(encoding="utf-8", errors="ignore")
            or "CyclicDependencyError" in p.read_text(encoding="utf-8", errors="ignore")
            for p in (root / "src").glob("**/*.py")
            if p.is_file()
            and ".worktrees" not in p.relative_to(root).parts
            and ".venv" not in p.relative_to(root).parts
        )
        if (root / "src").is_dir()
        else False
    )
    if not (has_bundle or has_taskand_policy or capsule_files or has_schemas or has_src_dag):
        findings.append(_err(
            "GOV-TASKAND-MISSING",
            "Repository requires wellmanifest/taskand but no capsule contracts, task DAG definitions or task orchestration modules were found.",
            str(root),
            "Define task capsules, schemas, or DAG dependency execution per wellmanifest/taskand.",
        ))
    return findings


def check_nl_uri_dsl_llm_pack(root: Path) -> List[Finding]:
    """Validate wellmanifest/nl-uri-dsl-llm profiles, schemas, NL plans, process exchanges, and snapshots."""
    findings: List[Finding] = []
    profile_files = _existing_files(root, ("profiles/semantic-*.json", ".governance/nl-uri-profile.json"))
    artifact_files = _existing_files(root, (
        "conformance/nl-uri*.json",
        "conformance/process-exchange*.json",
        "conformance/snapshot*.json",
        ".governance/nl-uri*.json",
    ))
    has_schemas = (
        (root / "schemas" / "process-uri.schema.json").is_file()
        and (root / "schemas" / "conversational-process-snapshot.schema.json").is_file()
    )
    has_consumer_bindings = any(
        (root / p).is_file()
        for p in ("dockuri.json", "agent/dockuri.yaml", "dsl_registry.json", "grammar.json")
    ) or any(
        p.is_file()
        for pat in ("**/dsl_registry.json", "**/nluri.py", "**/dockuri_proc.py")
        for p in root.glob(pat)
        if ".worktrees" not in p.relative_to(root).parts and ".venv" not in p.relative_to(root).parts
    )

    if not (profile_files or artifact_files or has_schemas or has_consumer_bindings):
        return [_err(
            "GOV-NL-URI-MISSING",
            "Repository requires wellmanifest/nl-uri-dsl-llm but no semantic profile, NL-to-URI schema, or URI/DSL binding was found.",
            str(root),
            "Add profiles/semantic-v1.json, NL-to-URI schemas, or canonical URI/DSL routing artifacts.",
        )]

    for path in profile_files:
        rel = _rel(root, path)
        try:
            doc = _unique_json_load(path)
        except Exception as exc:
            findings.append(_err("GOV-NL-URI-PROFILE-INVALID", f"Invalid semantic profile JSON in {rel}: {exc}", rel,
                                 "Provide a valid duplicate-free JSON object."))
            continue
        if doc.get("envelope") != "wellmanifest.nl-plan/v1":
            findings.append(_err("GOV-NL-URI-PROFILE-ENVELOPE",
                                 f"{rel} must bind envelope 'wellmanifest.nl-plan/v1'.", rel,
                                 "Set envelope to 'wellmanifest.nl-plan/v1'."))
        if doc.get("lexical_admission") is not False or doc.get("compilation_executes") is not False:
            findings.append(_err("GOV-NL-URI-PROFILE-SAFETY",
                                 f"{rel} must enforce lexical_admission=false and compilation_executes=false.", rel,
                                 "Keep NL compilation side-effect-free and disallow lexical authority admission."))
        exch = doc.get("exchange")
        if not isinstance(exch, dict) or exch.get("authority_from_envelope") is not False:
            findings.append(_err("GOV-NL-URI-EXCHANGE-AUTHORITY",
                                 f"{rel} exchange contract must set authority_from_envelope=false.", rel,
                                 "Set exchange.authority_from_envelope to false."))

    for path in artifact_files:
        rel = _rel(root, path)
        try:
            doc = _unique_json_load(path)
        except Exception as exc:
            findings.append(_err("GOV-NL-URI-DOC-INVALID", f"Invalid NL-URI JSON in {rel}: {exc}", rel,
                                 "Provide a valid duplicate-free JSON object."))
            continue

        schema = doc.get("schema")
        if schema == "wellmanifest.nl-plan/v1":
            if doc.get("status") not in {"ok", "clarify", "unsupported"}:
                findings.append(_err("GOV-NL-URI-PLAN-STATUS",
                                     f"{rel} nl-plan status must be 'ok', 'clarify', or 'unsupported'.", rel,
                                     "Use a valid wellmanifest.nl-plan/v1 status."))
            op = doc.get("operation")
            if doc.get("status") == "ok" and (not isinstance(op, str) or not URI_OPERATION_RE.match(op)):
                findings.append(_err("GOV-NL-URI-PLAN-URI",
                                     f"{rel} status='ok' plan must specify a canonical operation URI.", rel,
                                     "Set operation to 'scheme://authority/path'."))
        elif schema == "wellmanifest.process-exchange/v1":
            if doc.get("kind") not in {"request", "result"}:
                findings.append(_err("GOV-NL-URI-EXCHANGE-KIND", f"{rel} kind must be 'request' or 'result'.", rel,
                                     "Set kind to 'request' or 'result'."))
            for urn_field in ("messageUrn", "requestUrn"):
                if not UUID_URN_RE.match(str(doc.get(urn_field) or "")):
                    findings.append(_err("GOV-NL-URI-EXCHANGE-URN",
                                         f"{rel} {urn_field} must be a canonical urn:uuid:... identifier.", rel,
                                         "Use urn:uuid:<v4> identifiers for exchange messages."))
            if not URI_OPERATION_RE.match(str(doc.get("operation") or "")):
                findings.append(_err("GOV-NL-URI-EXCHANGE-OP", f"{rel} operation must be a canonical URI.", rel,
                                     "Use scheme://authority/path for operation."))
            if not HEX64_RE.match(str(doc.get("contractDigest") or "")):
                findings.append(_err("GOV-NL-URI-EXCHANGE-DIGEST", f"{rel} contractDigest must be 64-hex SHA-256.", rel,
                                     "Bind exchange messages to a 64-hex contractDigest."))
            effects = doc.get("effects")
            allowed_eff = {"read", "write", "execute", "network"}
            if not isinstance(effects, list) or not effects or not set(effects).issubset(allowed_eff):
                findings.append(_err("GOV-NL-URI-EXCHANGE-EFFECTS",
                                     f"{rel} effects must be a non-empty subset of {sorted(allowed_eff)}.", rel,
                                     "Declare valid effect classes on process-exchange envelopes."))
        elif schema == "wellmanifest.conversational-process-snapshot/v1":
            chat = doc.get("chat")
            procs = doc.get("processes")
            if not isinstance(doc.get("state"), dict) or not isinstance(chat, dict) or not isinstance(procs, dict):
                findings.append(_err("GOV-NL-URI-SNAPSHOT-SHAPE",
                                     f"{rel} snapshot requires object 'state', 'chat', and 'processes' sections.", rel,
                                     "Include state, chat, and processes objects per snapshot/v1."))
            else:
                items = procs.get("items")
                if not isinstance(items, list):
                    findings.append(_err("GOV-NL-URI-SNAPSHOT-PROCS", f"{rel} processes.items must be an array.", rel,
                                         "Provide an array for processes.items."))
                else:
                    for idx, item in enumerate(items):
                        if not isinstance(item, dict):
                            findings.append(_err("GOV-NL-URI-SNAPSHOT-PROCS",
                                                 f"{rel} processes.items[{idx}] must be an object.", rel,
                                                 "Use structured process items."))
                            continue
                        if not PROC_URN_RE.match(str(item.get("urn") or "")) or not PROCESS_URI_RE.match(str(item.get("uri") or "")):
                            findings.append(_err("GOV-NL-URI-SNAPSHOT-URI",
                                                 f"{rel} processes.items[{idx}] requires canonical urn:*:proc:* and process://<host>/... URI.",
                                                 rel, "Bind snapshot process items to canonical URN and process:// URI."))
        else:
            findings.append(_err("GOV-NL-URI-SCHEMA-UNKNOWN",
                                 f"{rel} has unsupported NL-URI schema '{schema}'.", rel,
                                 "Use wellmanifest.nl-plan/v1, wellmanifest.process-exchange/v1, or wellmanifest.conversational-process-snapshot/v1."))

    return findings
