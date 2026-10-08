"""Read-only domain SSOT diagnostics from explicit, source-bound declarations.

``analyze_ssot(observation, declarations)`` accepts a wellman.observation/v1
and a closed declaration document with schema, observation_digest and records.
Each record declares id, domain, kind, key, component_id, role, content_digest,
evidence_refs, source_id and source_digest. Roles are owner/consumer/projection.
Consumers and projections name their owner by source_id. A projection additionally
binds the owner's content_digest in source_digest. Digests describe declared
contract content, not semantic equivalence or authority. Scanner/LLM output must
be reviewed upstream; this API neither infers ownership from names nor applies
refactoring. Missing evidence produces defer, never evidence of absence.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime

from wellman.selection_contracts import ContractError, canonical_bytes, payload_digest, validate_document

KINDS = {"command", "query", "event", "error", "rule", "model"}
ROLES = {"owner", "consumer", "projection"}
FIELDS = {"id", "domain", "kind", "key", "component_id", "role", "content_digest",
          "evidence_refs", "source_id", "source_digest"}
HEX = re.compile(r"[a-f0-9]{64}\Z")


def analyze_ssot(observation, declarations):
    """Return deterministic findings and non-executable refactoring proposals.

    At most 2,000 records/20 MiB are accepted. The observation must describe
    the same sources as the declaration document. This is an advisory API;
    even a verified observation is not a grant to change source or governance.
    """
    validate_document(observation)
    if len(canonical_bytes(declarations)) > 20 * 1024 * 1024:
        raise ContractError("SSOT_DOCUMENT_BUDGET")
    if not isinstance(declarations, dict) or set(declarations) != {"schema", "observation_digest", "records"}:
        raise ContractError("SSOT_DOCUMENT_INVALID")
    if declarations["schema"] != "wellman.ssot-declarations/v1":
        raise ContractError("SSOT_SCHEMA_UNSUPPORTED")
    if declarations["observation_digest"] != payload_digest(observation):
        raise ContractError("SSOT_OBSERVATION_STALE")
    rows = declarations["records"]
    if not isinstance(rows, list) or len(rows) > 2000:
        raise ContractError("SSOT_RECORD_BUDGET")
    records = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ContractError("SSOT_RECORD_INVALID")
        for field in ("id", "domain", "kind", "key", "component_id", "role"):
            if (not isinstance(row[field], str) or not row[field].strip()
                    or row[field] != row[field].strip() or len(row[field]) > 256):
                raise ContractError("SSOT_IDENTIFIER_INVALID")
        if row["kind"] not in KINDS or row["role"] not in ROLES or row["id"] in records:
            raise ContractError("SSOT_KIND_ROLE_OR_ID_INVALID")
        for field in ("content_digest", "source_digest"):
            if row[field] is not None and (not isinstance(row[field], str) or not HEX.fullmatch(row[field])):
                raise ContractError("SSOT_DIGEST_INVALID")
        if row["source_id"] is not None and (not isinstance(row["source_id"], str) or not row["source_id"].strip() or len(row["source_id"]) > 256):
            raise ContractError("SSOT_REFERENCE_INVALID")
        refs = row["evidence_refs"]
        if not isinstance(refs, list) or len(refs) > 32 or any(not isinstance(r, str) or not r or len(r) > 256 for r in refs):
            raise ContractError("SSOT_EVIDENCE_INVALID")
        if row["role"] == "owner" and (row["source_id"] is not None or row["source_digest"] is not None):
            raise ContractError("SSOT_OWNER_CANNOT_BE_PROJECTION")
        records[row["id"]] = row
    components = {c["id"]: c for c in observation["components"]}
    repositories = {r["id"]: r for r in observation["repositories"]}
    artifacts = {a["id"]: a for a in observation["artifacts"]}
    if any(len(mapping) != len(observation[name]) for mapping, name in
           ((components, "components"), (repositories, "repositories"), (artifacts, "artifacts"))):
        raise ContractError("SSOT_AMBIGUOUS_OBSERVATION")
    def moment(value):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ContractError("SSOT_OBSERVATION_TIME") from error
        if result.tzinfo is None:
            raise ContractError("SSOT_OBSERVATION_TIME")
        return result
    start, end = moment(observation["started_at"]), moment(observation["finished_at"])
    if start > end:
        raise ContractError("SSOT_OBSERVATION_INTERVAL")
    findings = []
    def finding(code, group, members, action="review"):
        ids = sorted(r["id"] for r in members)
        findings.append({"code": code, "domain": group[0], "kind": group[1], "key": group[2],
                         "record_ids": ids, "evidence_refs": sorted({e for r in members for e in r["evidence_refs"]}),
                         "action": action})
    groups = defaultdict(list)
    uncertain = set()
    for row in records.values():
        group = row["domain"], row["kind"], row["key"]
        groups[group].append(row)
        c = components.get(row["component_id"])
        repo = repositories.get(c["repository_id"]) if c else None
        known = c and c["boundary"] == "confirmed" and repo and repo["identity"] == "confirmed" and repo["source_digest"] is not None
        refs = row["evidence_refs"]
        for ref in refs:
            artifact = artifacts.get(ref)
            known = known and artifact and artifact["freshness"] == "verified" and artifact["origin_observation_id"] == observation["observation_id"]
            known = known and any(s["tool"] == artifact["producer"] and ref in s["artifact_refs"] and
                s["component_id"] in (None, row["component_id"]) and s["status"] == "complete" and
                s["coverage"] == "complete" and not s["truncated"] and s["exit_code"] == 0 and not s["errors"] and
                start <= moment(s["started_at"]) <= moment(s["finished_at"]) <= end for s in observation["stages"])
        for issue in observation["quality_issues"]:
            affected = set(issue["affected_refs"])
            if (issue["severity"] == "error" or issue["code"] == "SOURCE_CHANGED_DURING_SCAN") and (
                    not affected or affected & {row["component_id"], *(refs), c["repository_id"] if c else ""}):
                known = False
        if not known or not refs or row["content_digest"] is None:
            uncertain.add(group)
    for group, members in sorted(groups.items()):
        if group in uncertain:
            finding("SSOT_EVIDENCE_INSUFFICIENT", group, members, "defer")
            continue
        owners = [r for r in members if r["role"] == "owner"]
        if not owners:
            finding("SSOT_OWNER_UNDECLARED", group, members)
            continue
        if len(owners) > 1:
            finding("SSOT_MULTIPLE_OWNERS", group, owners)
            continue
        owner = owners[0]
        for row in sorted(members, key=lambda r: r["id"]):
            if row["role"] == "owner":
                continue
            if row["source_id"] != owner["id"]:
                finding("SSOT_SOURCE_REFERENCE_INVALID", group, [owner, row])
            elif row["role"] == "projection":
                if row["source_digest"] is None:
                    finding("SSOT_PROJECTION_BINDING_MISSING", group, [owner, row], "defer")
                elif row["source_digest"] != owner["content_digest"]:
                    finding("SSOT_PROJECTION_STALE", group, [owner, row])
                # Content hashes can differ across transport formats. Without a
                # reviewed semantic adapter they cannot prove divergence.
    actions = {
        "SSOT_OWNER_UNDECLARED": "Declare the reviewed canonical owner for this domain contract.",
        "SSOT_MULTIPLE_OWNERS": "Review competing ownership; choose an owner and preserve distinct domain behavior before changing consumers.",
        "SSOT_SOURCE_REFERENCE_INVALID": "Bind this consumer or projection to the reviewed owner of the same domain and contract kind.",
        "SSOT_PROJECTION_STALE": "Prepare regeneration from the current owner using a reviewed adapter; validate transport and behavior compatibility.",
    }
    proposals = [{"code": f["code"], "domain": f["domain"], "kind": f["kind"], "key": f["key"],
                  "record_ids": f["record_ids"], "evidence_refs": f["evidence_refs"], "next_action": actions[f["code"]],
                  "required_validation": ["owner review", "consumer contract compatibility", "behavior-preservation tests"],
                  "executable": False} for f in findings if f["action"] == "review"]
    normalized = {**declarations, "records": [dict(records[k], evidence_refs=sorted(set(records[k]["evidence_refs"]))) for k in sorted(records)]}
    result = {"schema": "wellman.ssot-analysis/v1", "observation_digest": payload_digest(observation),
              "declarations_digest": payload_digest(normalized), "grants_authority": False, "applied": False,
              "coverage": "declared-contracts-only", "findings": findings, "refactoring_proposals": proposals,
              "limitations": ["No discovery of undeclared contracts", "No semantic equivalence inferred from matching hashes",
                              "No adapter execution, source changes, standards adoption or approval"]}
    result["analysis_digest"] = payload_digest(result)
    return result
