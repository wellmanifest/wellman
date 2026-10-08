from copy import deepcopy

import pytest

from wellman.selection_contracts import ContractError, payload_digest
from wellman.ssot import analyze_ssot


def inputs():
    obs = {"schema": "wellman.observation/v1", "observation_id": "scan-1",
        "started_at": "2026-10-08T00:00:00Z", "finished_at": "2026-10-08T00:01:00Z", "grants_authority": False,
        "repositories": [{"id": "owner/repo", "path": ".", "head": "a"*40, "identity": "confirmed",
                          "source_digest": "1"*64, "local_changes_digest": "2"*64}],
        "components": [{"id": "lib", "repository_id": "owner/repo", "path": ".", "boundary": "confirmed",
                        "manifests": ["package.json"], "evidence_refs": ["contracts"]}],
        "scope": {"roots": ["."], "files_digest": "3"*64, "policy_digest": "4"*64, "exclusions": []}, "tools": [],
        "stages": [{"id": "contracts-stage", "tool": "contracts", "component_id": "lib",
                    "started_at": "2026-10-08T00:00:00Z", "finished_at": "2026-10-08T00:01:00Z",
                    "status": "complete", "exit_code": 0, "truncated": False, "coverage": "complete",
                    "errors": [], "artifact_refs": ["contracts"]}],
        "artifacts": [{"id": "contracts", "path": "contracts.json", "media_type": "application/json",
                       "size_bytes": 3, "sha256": "5"*64, "producer": "contracts",
                       "origin_observation_id": "scan-1", "freshness": "verified"}],
        "features": [], "metrics": [], "quality_issues": []}
    decl = {"schema": "wellman.ssot-declarations/v1", "observation_digest": payload_digest(obs), "records": []}
    return obs, decl


def record(id="owner", role="owner", **values):
    return {"id": id, "domain": "billing", "kind": "rule", "key": "quota", "component_id": "lib",
            "role": role, "content_digest": "6"*64, "evidence_refs": ["contracts"],
            "source_id": None if role == "owner" else "owner", "source_digest": None, **values}


def run(rows, change=None):
    obs, decl = inputs()
    if change:
        change(obs)
    decl["observation_digest"] = payload_digest(obs)
    decl["records"] = rows
    return analyze_ssot(obs, decl)


def codes(result):
    return {f["code"] for f in result["findings"]}


def test_valid_owner_consumer_and_transport_projection_do_not_imply_divergence():
    r = run([record(), record("cli", "consumer"),
             record("json", "projection", source_digest="6"*64, content_digest="7"*64)])
    assert r["findings"] == r["refactoring_proposals"] == []
    assert r["coverage"] == "declared-contracts-only"
    assert not r["grants_authority"] and not r["applied"]


def test_competing_owners_propose_review_never_automatic_deduplication():
    r = run([record(), record("other")])
    assert codes(r) == {"SSOT_MULTIPLE_OWNERS"}
    assert not r["refactoring_proposals"][0]["executable"]
    assert "behavior-preservation tests" in r["refactoring_proposals"][0]["required_validation"]


def test_domain_and_contract_kind_are_separate_ssot_boundaries():
    assert not run([record(), record("other", domain="identity"), record("query", kind="query")])["findings"]


@pytest.mark.parametrize("rows,code", [
    ([record("consumer", "consumer")], "SSOT_OWNER_UNDECLARED"),
    ([record(), record("consumer", "consumer", source_id="other")], "SSOT_SOURCE_REFERENCE_INVALID"),
    ([record(), record("json", "projection", source_digest="7"*64)], "SSOT_PROJECTION_STALE"),
    ([record(), record("json", "projection")], "SSOT_PROJECTION_BINDING_MISSING"),
])
def test_missing_binding_and_stale_projection_are_explicit(rows, code):
    assert codes(run(rows)) == {code}


@pytest.mark.parametrize("change", [
    lambda o: o["stages"][0].update(status="partial"),
    lambda o: o["stages"][0].update(status="partial", truncated=True),
    lambda o: o["stages"][0].update(status="failed", exit_code=1),
    lambda o: o["stages"][0].update(component_id="other"),
    lambda o: o["artifacts"][0].update(freshness="legacy_unverified"),
    lambda o: o["artifacts"][0].update(origin_observation_id="scan-old"),
    lambda o: o["repositories"][0].update(source_digest=None),
    lambda o: o["components"][0].update(boundary="unknown"),
    lambda o: o["stages"][0].update(finished_at="2026-10-09T00:01:00Z"),
    lambda o: o["quality_issues"].append({"code": "SOURCE_CHANGED_DURING_SCAN", "severity": "warning",
        "message": "changed", "affected_refs": ["contracts"], "next_action": "rescan"}),
])
def test_incomplete_or_unbound_observation_defers_entire_domain_contract(change):
    r = run([record(), record("other")], change)
    assert codes(r) == {"SSOT_EVIDENCE_INSUFFICIENT"}
    assert r["findings"][0]["action"] == "defer" and not r["refactoring_proposals"]


@pytest.mark.parametrize("values", [{"evidence_refs": []}, {"evidence_refs": ["missing"]},
                                    {"component_id": "missing"}, {"content_digest": None}])
def test_unknown_declaration_evidence_never_becomes_owner_conflict(values):
    assert codes(run([record(), record("other", **values)])) == {"SSOT_EVIDENCE_INSUFFICIENT"}


def test_stale_digest_duplicate_ids_unknown_fields_and_budgets_fail():
    obs, decl = inputs()
    with pytest.raises(ContractError, match="STALE"):
        analyze_ssot(obs, {**decl, "observation_digest": "0"*64})
    for rows in ([record(), record()], [record(role="execute")], [dict(record(), command="rm -rf /")],
                 [record(content_digest="invalid")], [record(source_id="projection")],
                 [record(domain="billing ")], [record()]*2001):
        with pytest.raises(ContractError):
            analyze_ssot(obs, {**decl, "records": rows})


def test_input_order_is_deterministic_and_inputs_are_immutable():
    obs, decl = inputs()
    decl["records"] = [record("second"), record("first")]
    before = deepcopy((obs, decl))
    a = analyze_ssot(obs, decl)
    b = analyze_ssot(obs, {**decl, "records": list(reversed(decl["records"]))})
    assert a == b
    assert (obs, decl) == before
    assert a["analysis_digest"] == payload_digest({k: v for k, v in a.items() if k != "analysis_digest"})
