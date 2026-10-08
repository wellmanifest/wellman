"""Optional native Planfile export of current, non-executable SSOT proposals.

The caller supplies an explicit external project and a source verification
context containing repository_roots, adoptions and artifact_root (plus optional
inventory_options). Inputs are recomputed through analyze_ssot; serialized LLM
plans are never accepted. This adapter does not run or synchronize tasks and
creates human review backlog records, not implementation authorization.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from wellman.selection_contracts import ContractError, payload_digest
from wellman.selection_plan import assert_repository_current
from wellman.ssot import analyze_ssot

LABELS = {"wellman-ssot", "actor:human", "autonomy-frontier"}
QUEUE = "wellman-ssot-review"
TOOL = "wellman.ssot-analysis"


def export_ssot_backlog(observation, declarations, project, *, context):
    """Return a local export receipt, preserving terminal and owned tickets.

    Requires optional Planfile 0.1.126. Live source/index/adoption and all saved
    artifact hashes are verified before and after waiting for its mutation lock.
    Stable keys bind repository/component identities and domain contract/finding,
    while refreshed analysis digests stay in source.context. No source mutation,
    remote effect or executable action is performed. Errors return ok=False.
    """
    try:
        if project is None or not isinstance(context, dict):
            raise ContractError("Explicit Planfile project and SSOT context required")
        observation, declarations, context = deepcopy(
            (observation, declarations, context)
        )
        if not context.get("artifact_root"):
            raise ContractError("Explicit saved artifact root required")
        roots = context["repository_roots"]
        if not isinstance(roots, dict) or not isinstance(
            context.get("adoptions"), dict
        ):
            raise ContractError("Invalid SSOT repository/adoption context")
        if context.get("inventory_options") is not None and not isinstance(
            context["inventory_options"], dict
        ):
            raise ContractError("Invalid SSOT inventory options")
        project = Path(project).absolute()
        artifacts = Path(context["artifact_root"]).absolute()
        # Keep the new backlog outside both sources and evidence snapshots.
        for root in [artifacts, *(Path(r).absolute() for r in roots.values())]:
            if project == root or root in project.parents or project in root.parents:
                raise ContractError(
                    "Planfile project must be separate from sources and artifacts"
                )

        def check():
            if any(p.is_symlink() for p in (project, *project.parents)):
                raise ContractError("Planfile project must not traverse symlinks")
            storage = project / ".planfile"
            if storage.is_symlink() or (
                storage.exists() and any(p.is_symlink() for p in storage.rglob("*"))
            ):
                raise ContractError("Planfile storage contains a symlink")
            assert_repository_current(
                observation,
                context["adoptions"],
                roots,
                inventory_options=context.get("inventory_options"),
                artifact_root=artifacts,
            )

        analysis = analyze_ssot(observation, declarations)
        check()
        import planfile

        if getattr(planfile, "__version__", None) != "0.1.126":
            raise ContractError(
                "Unsupported Planfile adapter version; expected 0.1.126"
            )
        from planfile.core.models import Ticket
        from planfile.core.store import Store

        for name in (
            "mutation_lock",
            "ticket_records",
            "get_ticket",
            "_next_id_unlocked",
            "_create_ticket_unlocked",
            "_update_ticket_unlocked",
        ):
            if not callable(getattr(Store, name, None)):
                raise ContractError(
                    "Unsupported native Planfile store capability: " + name
                )

        components = {c["id"]: c["repository_id"] for c in observation["components"]}
        records = {r["id"]: r for r in declarations["records"]}
        proposals = analysis["refactoring_proposals"]
        keys = [
            payload_digest(
                {
                    "domain": p["domain"],
                    "kind": p["kind"],
                    "key": p["key"],
                    "code": p["code"],
                    "record_ids": sorted(p["record_ids"]),
                    "components": [
                        list(pair)
                        for pair in sorted(
                            {
                                (
                                    components[records[r]["component_id"]],
                                    records[r]["component_id"],
                                )
                                for r in p["record_ids"]
                            }
                        )
                    ],
                }
            )
            for p in proposals
        ]
        if len(set(keys)) != len(keys):
            raise ContractError("Ambiguous SSOT proposal identity")
        rows = []
        if proposals:
            store = Store(project)
            if store.project_dir != project:
                raise ContractError(
                    "Explicit project resolves to another Planfile boundary"
                )
            with store.mutation_lock():
                check()
                if not store.is_initialized():
                    store.init()
                inventory = list(store.ticket_records(sprint="all"))
                existing = {}
                for key in keys:
                    matches = [
                        r
                        for r in inventory
                        if "dedupe:wellman-ssot:" + key in (r.get("labels") or [])
                    ]
                    if len(matches) > 1:
                        raise ContractError("Ambiguous existing SSOT proposal key")
                    if matches:
                        ticket = store.get_ticket(matches[0]["id"], repair_index=False)
                        if ticket is None:
                            raise ContractError(
                                "SSOT proposal disappeared from native store"
                            )
                        existing[key] = ticket
                for key, proposal in zip(keys, proposals):
                    source = {
                        "tool": TOOL,
                        "version": "v1",
                        "context": {
                            "analysis_digest": analysis["analysis_digest"],
                            "observation_digest": analysis["observation_digest"],
                            "declarations_digest": analysis["declarations_digest"],
                            "proposal": proposal,
                            "grants_authority": False,
                        },
                    }
                    ticket = existing.get(key)
                    state = "created"
                    if ticket is None:
                        ticket = Ticket(
                            id=store._next_id_unlocked(),
                            name="Review SSOT: "
                            + proposal["code"]
                            + " / "
                            + proposal["key"],
                            status="open",
                            sprint="backlog",
                            labels=sorted(LABELS | {"dedupe:wellman-ssot:" + key}),
                            executor={"kind": "human", "mode": "interactive"},
                            execution={"queue": QUEUE, "state": "pending"},
                            source=source,
                        )
                        store._create_ticket_unlocked(ticket)
                    elif str(getattr(ticket.status, "value", ticket.status)) in {
                        "done",
                        "canceled",
                        "failed",
                        "blocked",
                    }:
                        state = "preserved_terminal"
                    elif not _refreshable(ticket):
                        state = "preserved_owned"
                    else:
                        previous = ticket.source.model_dump(mode="json")
                        source = {
                            **previous,
                            **source,
                            "context": {**previous["context"], **source["context"]},
                        }
                        state = "reused"
                        if previous != source:
                            updated = store._update_ticket_unlocked(
                                ticket.id,
                                expected_updated_at=ticket.updated_at.isoformat(),
                                reason="Refresh evidence-bound SSOT review proposal",
                                actor="wellman.ssot-export",
                                source=source,
                            )
                            if updated is None:
                                raise ContractError(
                                    "SSOT proposal update lost its expected revision"
                                )
                            state = "updated"
                    rows.append({"id": ticket.id, "key": key, "state": state})
        return {
            "ok": True,
            "schema": "wellman.ssot-backlog-receipt/v1",
            "analysis_digest": analysis["analysis_digest"],
            "tickets": rows,
            "count": len(rows),
            "created": sum(r["state"] == "created" for r in rows),
            "deferred": sum(f["action"] == "defer" for f in analysis["findings"]),
            "target_projects": [str(project)] if rows else [],
            "remote_effects": False,
            "executable": False,
            "grants_authority": False,
        }
    except (
        ImportError,
        ContractError,
        KeyError,
        ValueError,
        TypeError,
        OSError,
        RuntimeError,
    ) as exc:
        return {
            "ok": False,
            "error": str(exc),
            "remote_effects": False,
            "executable": False,
            "grants_authority": False,
        }


def _refreshable(ticket):
    return (
        str(getattr(ticket.status, "value", ticket.status)) == "open"
        and ticket.sprint == "backlog"
        and not ticket.blocked_by
        and ticket.executor is not None
        and (ticket.executor.kind, ticket.executor.mode) == ("human", "interactive")
        and ticket.execution is not None
        and ticket.execution.state == "pending"
        and ticket.execution.queue == QUEUE
        and all(
            getattr(ticket.execution, f) is None
            for f in ("assigned_to", "started_at", "finished_at", "lease_expires_at")
        )
        and ticket.source is not None
        and ticket.source.tool == TOOL
        and ticket.source.version == "v1"
        and ticket.source.context.get("grants_authority") is False
        and ticket.inputs is None
        and LABELS <= set(ticket.labels)
    )
