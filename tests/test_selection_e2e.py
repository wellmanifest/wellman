"""Acceptance of read-only component planning and explicit human backlog export."""

import hashlib
import json
import subprocess
from copy import deepcopy

import pytest

from wellman.applicability import build_catalog
from wellman.cli import main
from wellman.fleet import feed_to_planfile
from wellman.selection_contracts import (
    ContractError,
    canonical_bytes,
    validate_document,
)
from wellman.selection_plan import (
    assert_repository_current,
    capture_repository,
    compose_selection_plan,
)

BASE = "wellmanifest/new-project"
DOCS = "wellmanifest/docs"
AGENT = "wellmanifest/agent"
PIN = "a" * 40


def write(root, path, data):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        canonical_bytes(data) if isinstance(data, dict) else data.encode()
    )


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def contents(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "product"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "remote", "add", "origin", "https://github.com/acme/components.git")
    write(
        root,
        "package.json",
        {"private": True, "workspaces": ["library", "executor", "desktop"]},
    )
    for name in ("library", "executor", "desktop"):
        write(
            root,
            name + "/package.json",
            {"name": name, "version": "1.0.0", "source": "src/main.py"},
        )
        write(root, name + "/src/main.py", "value = 1\n")
    write(root, "bench-results/result.json", {"runs": 100, "purity": "100% pure"})
    write(root, "AGENTS.md", "existing instructions\n")
    write(root, ".github/workflows/ci.yml", "name: existing-ci\n")
    write(root, "package-lock.json", {"lockfileVersion": 3})
    write(
        root,
        ".governance/manifest.json",
        {
            "schema": "new-project.governance/v2",
            "standard": {"id": BASE, "version": "1.0.0"},
            "profile": "baseline",
        },
    )
    write(
        root,
        ".governance/manifest.lock.json",
        {
            "schema": "new-project.lock/v1",
            "standard": {
                "id": BASE,
                "version": "1.0.0",
                "sourceRepository": BASE,
                "sourceRevision": PIN,
                "publicationStatus": "published",
            },
            "managedFiles": {
                "AGENTS.md": hashlib.sha256(
                    (root / "AGENTS.md").read_bytes()
                ).hexdigest()
            },
        },
    )
    write(
        root,
        ".governance/package-manifest.json",
        {
            "schema": "new-project.package-manifest/v1",
            "files": [
                {
                    "source": "template/AGENTS.md",
                    "target": "AGENTS.md",
                    "strategy": "managed",
                    "executable": False,
                }
            ],
        },
    )
    git(root, "add", ".")
    git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "Fixture",
    )
    options = {"classification": {"runtime_artifact": ["bench-results/**"]}}
    bundle = capture_repository(root, observation_id="acceptance-components", **options)
    cat = build_catalog(
        {identifier: PIN for identifier in (BASE, DOCS, AGENT)},
        revision="b" * 40,
        trusted_source="explicit-acceptance-fixture",
        metadata={
            identifier: {
                "managed_files": ["AGENTS.md"],
                "validators": ["review contract"],
            }
            for identifier in (BASE, DOCS, AGENT)
        },
    )
    context = {
        "observation": bundle["observation"],
        "catalog": cat,
        "adoptions": bundle["adoptions"],
        "repository_roots": {"acme/components": root},
        "inventory_options": options,
    }
    return root, bundle, cat, context


def test_component_plan_keep_add_defer_and_explicit_export_preserve_source(
    workspace, tmp_path
):
    root, bundle, catalog, context = workspace
    before = contents(root)
    inventory = bundle["inventory"]
    assert {c["path"] for c in inventory["components"]} == {
        ".",
        "library",
        "executor",
        "desktop",
    }
    assert (
        next(f for f in inventory["files"] if f["path"] == "bench-results/result.json")[
            "class"
        ]
        == "runtime_artifact"
    )
    plan = compose_selection_plan(bundle["observation"], catalog, bundle["adoptions"])
    validate_document(plan)
    decisions = [
        d for d in plan["decisions"] if d["standard_id"] in (BASE, DOCS, AGENT)
    ]
    assert {d["action"] for d in decisions if d["standard_id"] == BASE} == {"keep"}
    assert {d["action"] for d in decisions if d["standard_id"] == DOCS} == {"add"}
    assert {d["action"] for d in decisions if d["standard_id"] == AGENT} == {"defer"}
    assert not plan["executable"] and not plan["grants_authority"]
    assert not (root / ".planfile").exists()
    pytest.importorskip("planfile.core.store")
    exported = feed_to_planfile(plan, tmp_path / "review", selection_context=context)
    assert exported["ok"] and not exported["remote_effects"], exported
    from planfile.core.store import Store

    tickets = Store(tmp_path / "review").list_tickets(sprint="all")
    assert all(t.source.context["proposal"]["standard_id"] != BASE for t in tickets)
    assert all(
        t.source.context["plan_hash"] == plan["plan_hash"]
        and not t.source.context["grants_authority"]
        and t.execution.state == "pending"
        and t.inputs is None
        for t in tickets
    )
    assert contents(root) == before


def test_local_drift_is_a_repair_proposal_without_overwrite(workspace):
    root, _, catalog, _ = workspace
    (root / "AGENTS.md").write_text("local customization\n")
    bundle = capture_repository(
        root, classification={"runtime_artifact": ["bench-results/**"]}
    )
    before = contents(root)
    plan = compose_selection_plan(bundle["observation"], catalog, bundle["adoptions"])
    decision = next(d for d in plan["decisions"] if d["standard_id"] == BASE)
    assert decision["action"] == "repair"
    assert "LOCAL_CHANGES_MUST_BE_PRESERVED" in decision["limitations"]
    assert not plan["executable"] and contents(root) == before


@pytest.mark.parametrize(
    "problem", ["partial", "failed", "missing", "legacy_unverified", "stale"]
)
def test_unreliable_inventory_cannot_authorize_a_proposal(workspace, problem):
    root, bundle, catalog, _ = workspace
    obs = deepcopy(bundle["observation"])
    artifact = next(a for a in obs["artifacts"] if a["id"] == "inventory")
    stage = next(s for s in obs["stages"] if "inventory" in s["artifact_refs"])
    if problem in ("stale", "legacy_unverified"):
        artifact["freshness"] = problem
    else:
        stage.update(
            status=problem,
            coverage="unknown",
            exit_code=1 if problem == "failed" else None,
            truncated=False,
        )
    before = contents(root)
    plan = compose_selection_plan(obs, catalog, bundle["adoptions"])
    assert (
        next(d for d in plan["decisions"] if d["standard_id"] == DOCS)["action"]
        == "defer"
    )
    assert not plan["executable"] and not plan["grants_authority"]
    assert contents(root) == before


def test_cli_snapshot_plan_and_stale_source_refusal_before_export(
    workspace, tmp_path, capsys
):
    root, bundle, catalog, _ = workspace
    snapshot = tmp_path / "snapshot"
    for name, data in (
        ("inventory", bundle["inventory"]),
        ("adoption", bundle["adoptions"]["acme/components"]),
        ("observation", bundle["observation"]),
        ("catalog", catalog),
        (
            "policy",
            {
                "classification": {"runtime_artifact": ["bench-results/**"]},
                "exclusions": [],
            },
        ),
    ):
        write(snapshot, name + ".json", data)
    args = [
        "recommend",
        "--root",
        str(root),
        "--selection-plan",
        "--catalog",
        str(snapshot / "catalog.json"),
        "--observation",
        str(snapshot / "observation.json"),
        "--scope-policy",
        str(snapshot / "policy.json"),
        "--json",
    ]
    before = contents(root)
    assert main(args) == 0
    plan = json.loads(capsys.readouterr().out)
    validate_document(plan)
    assert plan["observation_id"] == "acceptance-components"
    assert contents(root) == before
    (root / "library/src/main.py").write_text("value = 2\n")
    assert main([*args, "--export-planfile", str(tmp_path / "review")]) != 0
    assert "PLAN_STALE" in capsys.readouterr().err
    assert not (tmp_path / "review/.planfile").exists()


def test_snapshot_artifact_tampering_is_rejected(workspace, tmp_path):
    _, bundle, _, context = workspace
    snapshot = tmp_path / "snapshot"
    write(snapshot, "inventory.json", bundle["inventory"])
    write(snapshot, "adoption.json", bundle["adoptions"]["acme/components"])
    write(snapshot, "inventory.json", {"changed": True})
    with pytest.raises(ContractError, match="PLAN_STALE"):
        assert_repository_current(
            bundle["observation"],
            bundle["adoptions"],
            context["repository_roots"],
            inventory_options=context["inventory_options"],
            artifact_root=snapshot,
        )
