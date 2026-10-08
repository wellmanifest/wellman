"""Compose evidence-bound recommendations; no adoption or analyzer execution."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from wellman.adoption_inspection import inspect_adoption
from wellman.applicability import resolve_applicability
from wellman.components import inventory_repository
from wellman.evidence import _path
from wellman.selection_contracts import (
    MAX_DOCUMENT_BYTES,
    ContractError,
    canonical_bytes,
    payload_digest,
    plan_digest,
    validate_document,
)

VERSION = "wellman.selection-observation/v1"


def _stamp():
    return datetime.now(timezone.utc).isoformat()


def _identity(inventory):
    return {
        key: inventory[key]
        for key in (
            "repository_id",
            "identity",
            "head",
            "source_digest",
            "local_changes_digest",
            "scope_digest",
            "complete",
        )
    }


def _issue(item):
    return {
        "code": item["code"],
        "severity": "warning",
        "message": item.get("message", item["code"].replace("_", " ").lower()),
        "affected_refs": item.get(
            "affected_refs", [item["path"]] if item.get("path") else []
        ),
        "next_action": item.get(
            "next_action", "Inspect the diagnostic before preparing changes."
        ),
    }


def capture_repository(
    root, *, classification=None, exclusions=(), observation_id=None
):
    """Observe source and adoption twice, without accepting project trust claims.

    Returned inventory/adoption payloads are in-memory artifacts. A snapshot
    writer must save their canonical bytes at the observation's relative paths.
    Runtime capabilities require separate source-bound evidence; filenames and
    imports do not establish agent, subscription or effectful execution roles.
    """
    root = Path(root).absolute()
    start = _stamp()
    options = {"classification": classification, "exclusions": exclusions}
    inventory = inventory_repository(root, **options)
    adoption = inspect_adoption(root, inventory=inventory)
    after = inventory_repository(root, **options)
    adoption_after = inspect_adoption(root, inventory=after)
    end = _stamp()
    stable = _identity(inventory) == _identity(after) and adoption == adoption_after
    complete = stable and inventory["complete"]
    oid = observation_id or "observation:" + payload_digest(
        {
            "inventory": inventory,
            "adoption": adoption,
            "started_at": start,
            "finished_at": end,
        }
    )
    config = payload_digest(
        {"classification": classification or {}, "exclusions": list(exclusions)}
    )
    artifacts = []
    stages = []
    tools = []
    for producer, name, data, covered in (
        ("wellman.inventory", "inventory", inventory, complete),
        (
            "wellman.adoption-inspection",
            "adoption",
            adoption,
            stable and adoption["coverage"] == "complete",
        ),
    ):
        raw = canonical_bytes(data)
        artifacts.append(
            {
                "id": name,
                "path": name + ".json",
                "media_type": "application/json",
                "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "producer": producer,
                "origin_observation_id": oid,
                "freshness": "verified" if stable else "stale",
            }
        )
        stages.append(
            {
                "id": name + "-stage",
                "tool": producer,
                "component_id": None,
                "started_at": start,
                "finished_at": end,
                "status": "complete" if covered else "partial",
                "exit_code": 0,
                "truncated": False,
                "coverage": "complete" if covered else "partial",
                "errors": [] if stable else ["SOURCE_CHANGED_DURING_SCAN"],
                "artifact_refs": [name],
            }
        )
        tools.append(
            {
                "id": producer,
                "version": VERSION,
                "adapter_version": VERSION,
                "output_schema": VERSION if name == "inventory" else adoption["schema"],
                "configuration_digest": config,
                "environment_digest": None,
                "effective_exclusions": inventory["exclusions"],
            }
        )
    components = [
        {
            key: c[key]
            for key in (
                "id",
                "repository_id",
                "path",
                "boundary",
                "manifests",
                "evidence_refs",
            )
        }
        for c in sorted(inventory["components"], key=lambda c: c["id"])
    ]
    # Boundary refs name the inventory artifact; file paths stay inside its payload.
    for component in components:
        component["evidence_refs"] = ["inventory"]
    features = [
        {
            "id": "repository:git",
            "component_id": c["id"],
            "state": "present"
            if stable and inventory["identity"] == "confirmed"
            else "unknown",
            "coverage": "complete" if complete else "partial",
            "evidence_refs": ["inventory"],
            "reasons": ["Git identity and manifest boundaries observed locally"],
        }
        for c in components
    ]
    issues = [
        _issue(item)
        for item in inventory["quality_issues"] + adoption.get("quality_issues", [])
    ]
    if not stable:
        issues.append(
            {
                "code": "SOURCE_CHANGED_DURING_SCAN",
                "severity": "error",
                "message": "Source or adoption changed between observations.",
                "affected_refs": ["inventory", "adoption"],
                "next_action": "Capture a stable snapshot again.",
            }
        )
    observation = {
        "schema": "wellman.observation/v1",
        "observation_id": oid,
        "started_at": start,
        "finished_at": end,
        "grants_authority": False,
        "repositories": [
            {
                "id": inventory["repository_id"],
                "path": str(root),
                "head": inventory["head"],
                "identity": inventory["identity"],
                "source_digest": inventory["source_digest"],
                "local_changes_digest": inventory["local_changes_digest"],
            }
        ],
        "components": components,
        "scope": {
            "roots": ["."],
            "files_digest": payload_digest(inventory["files"]),
            "policy_digest": config,
            "exclusions": inventory["exclusions"],
        },
        "tools": tools,
        "stages": stages,
        "artifacts": artifacts,
        "features": features,
        "metrics": [],
        "quality_issues": issues,
    }
    validate_document(observation)
    return {
        "observation": observation,
        "inventory": inventory,
        "adoptions": {inventory["repository_id"]: adoption},
    }


def compose_selection_plan(observation, catalog, adoptions, *, advisory=None):
    """Resolve and hash the complete, nonexecutable recommendation payload."""
    resolved = resolve_applicability(observation, catalog, adoptions, advisory=advisory)
    order = {id: i for i, id in enumerate(resolved["dependency_order"])}
    decisions = sorted(
        resolved["decisions"],
        key=lambda d: (
            d["repository_id"],
            d["component_id"],
            order.get(d["standard_id"], len(order)),
            d["standard_id"],
        ),
    )
    plan = {
        "schema": "wellman.selection-plan/v1",
        "mode": "recommendation",
        "grants_authority": False,
        "executable": False,
        "observation_id": observation["observation_id"],
        "observation_digest": payload_digest(observation),
        "catalog_digest": catalog["catalog_digest"],
        "rule_digest": resolved["rule_digest"],
        "source_digests": {
            r["id"]: payload_digest({"repository": r, "scope": observation["scope"]})
            for r in observation["repositories"]
        },
        "adoption_digests": {
            id: payload_digest(value) for id, value in sorted(adoptions.items())
        },
        "decisions": decisions,
        "quality_issues": observation["quality_issues"]
        + [_issue(d) for d in resolved["diagnostics"]],
    }
    plan["plan_hash"] = plan_digest(plan)
    validate_document(plan)
    return plan


def assert_plan_current(plan, observation, catalog, adoptions):
    """Reject changed inputs or edited decisions, even when self-rehashed."""
    validate_document(plan)
    expected = compose_selection_plan(observation, catalog, adoptions)
    if (
        not plan.get("plan_hash")
        or plan_digest(plan) != plan["plan_hash"]
        or plan_digest(expected) != plan["plan_hash"]
    ):
        raise ContractError("PLAN_STALE: recommendation or bound inputs changed")


def assert_repository_current(
    observation,
    adoptions,
    repository_roots,
    *,
    inventory_options=None,
    artifact_root=None,
):
    """Re-observe live source/index/adoption and optional saved artifact bytes.

    A hash identifies evidence bytes; it does not confer trust in a saved receipt.
    Callers verify scanner provenance separately before using that evidence.
    """
    validate_document(observation)
    if set(repository_roots) != {r["id"] for r in observation["repositories"]}:
        raise ContractError("PLAN_STALE: repository roots do not match observation")
    options = inventory_options or {}
    policy = payload_digest(
        {
            "classification": options.get("classification") or {},
            "exclusions": list(options.get("exclusions", ())),
        }
    )
    if policy != observation["scope"]["policy_digest"]:
        raise ContractError("PLAN_STALE: classification or exclusions changed")
    for repository in observation["repositories"]:
        root = Path(repository_roots[repository["id"]]).absolute()
        if str(root) != repository["path"]:
            raise ContractError("PLAN_STALE: repository path changed")
        fresh = inventory_repository(root, **options)
        current = {
            "id": fresh["repository_id"],
            "path": str(root),
            "head": fresh["head"],
            "identity": fresh["identity"],
            "source_digest": fresh["source_digest"],
            "local_changes_digest": fresh["local_changes_digest"],
        }
        if (
            current != repository
            or payload_digest(fresh["files"]) != observation["scope"]["files_digest"]
        ):
            raise ContractError("PLAN_STALE: source, index or scope changed")
        if inspect_adoption(root, inventory=fresh) != adoptions.get(repository["id"]):
            raise ContractError("PLAN_STALE: adoption changed")
    if artifact_root is not None:
        root = Path(artifact_root).absolute()
        if any(p.is_symlink() for p in (root, *root.parents)):
            raise ContractError("PLAN_STALE: unsafe artifact root")
        for artifact in observation["artifacts"]:
            path = _path(root, artifact["path"])
            if not path.is_file() or path.stat().st_size > MAX_DOCUMENT_BYTES:
                raise ContractError("PLAN_STALE: evidence missing or oversized")
            raw = path.read_bytes()
            if (
                len(raw) != artifact["size_bytes"]
                or hashlib.sha256(raw).hexdigest() != artifact["sha256"]
            ):
                raise ContractError("PLAN_STALE: evidence bytes changed")


def render_selection_plan(plan):
    validate_document(plan)
    lines = [
        "Recommendation " + str(plan.get("plan_hash", "unhashed")),
        "No execution authority. Review proposals before preparing changes.",
    ]
    for d in plan["decisions"]:
        lines.append(
            f"{d['repository_id']} / {d['component_id']}: {d['standard_id']} "
            f"{d['action']} ({d['applicability']})"
        )
        lines.append("  Reasons: " + ", ".join(d["reasons"]))
        lines.append(
            "  Current: "
            + str(d["current"]["revision"])
            + "; target: "
            + str(d["target_revision"])
        )
        lines.append(
            "  Files: "
            + ", ".join(d["managed_files"])
            + "; validators: "
            + ", ".join(d["validators"])
        )
        lines.append(
            "  Risk: "
            + d["risk"]
            + "; authorities: "
            + ", ".join(d["required_authorities"])
        )
        if d["limitations"]:
            lines.append("  Limitations: " + ", ".join(d["limitations"]))
    return "\n".join(lines) + "\n"
