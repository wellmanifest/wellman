import subprocess
from copy import deepcopy

import pytest

from wellman.applicability import build_catalog
from wellman.selection_contracts import (
    ContractError,
    canonical_bytes,
    payload_digest,
    plan_digest,
    validate_document,
)
from wellman.selection_plan import (
    assert_plan_current,
    assert_repository_current,
    capture_repository,
    compose_selection_plan,
    render_selection_plan,
)

STANDARD = "wellmanifest/new-project"
PIN = "a" * 40


@pytest.fixture
def selection(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "remote",
            "add",
            "origin",
            "https://github.com/owner/repo.git",
        ],
        check=True,
    )
    (root / "pyproject.toml").write_text('[project]\nname="library"\nversion="1.0.0"\n')
    (root / "library.py").write_text("value = 1\n")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "Fixture",
        ],
        check=True,
    )
    bundle = capture_repository(root, observation_id="test-scan")
    cat = build_catalog(
        {STANDARD: PIN},
        revision="b" * 40,
        trusted_source="explicit-test-catalog",
        metadata={
            STANDARD: {
                "managed_files": ["AGENTS.md"],
                "validators": ["review managed contract"],
                "effects": ["files"],
            }
        },
    )
    plan = compose_selection_plan(bundle["observation"], cat, bundle["adoptions"])
    context = {
        "observation": bundle["observation"],
        "catalog": cat,
        "adoptions": bundle["adoptions"],
        "repository_roots": {"owner/repo": root},
    }
    return root, bundle, cat, plan, context


def decision(plan):
    return next(d for d in plan["decisions"] if d["standard_id"] == STANDARD)


def test_live_capture_binds_inventory_adoption_and_baseline_proposal(selection):
    root, bundle, cat, plan, context = selection
    validate_document(bundle["observation"])
    validate_document(plan)
    assert decision(plan)["action"] == "add"
    assert not plan["executable"] and not plan["grants_authority"]
    assert_plan_current(plan, bundle["observation"], cat, bundle["adoptions"])
    assert_repository_current(
        bundle["observation"], bundle["adoptions"], context["repository_roots"]
    )
    assert not (root / ".governance").exists()


def test_exact_snapshot_is_deterministic_and_output_metadata_does_not_change_hash(
    selection,
):
    _, b, c, p, _ = selection
    assert (
        compose_selection_plan(
            deepcopy(b["observation"]), deepcopy(c), deepcopy(b["adoptions"])
        )
        == p
    )
    p["rendered_at"] = "2026-10-08T10:00:00Z"
    p["output_path"] = "somewhere/plan.json"
    assert plan_digest(p) == p["plan_hash"]
    assert_plan_current(p, b["observation"], c, b["adoptions"])


@pytest.mark.parametrize(
    "changed", ["evidence", "catalog", "adoption", "decision", "rehash"]
)
def test_changed_bound_input_or_edited_decision_is_stale(selection, changed):
    _, b, c, p, _ = selection
    if changed == "evidence":
        b["observation"]["artifacts"][0]["sha256"] = "f" * 64
    elif changed == "catalog":
        c["standards"][0]["revision"] = "d" * 40
    elif changed == "adoption":
        b["adoptions"]["owner/repo"]["coverage"] = "unknown"
    else:
        decision(p)["action"] = "keep"
        if changed == "rehash":
            p["plan_hash"] = plan_digest(p)
    with pytest.raises(ContractError):
        assert_plan_current(p, b["observation"], c, b["adoptions"])


@pytest.mark.parametrize(
    "changed", ["source", "untracked", "index", "origin", "adoption"]
)
def test_live_material_changes_are_stale(selection, changed):
    root, b, _, _, ctx = selection
    if changed == "source":
        (root / "library.py").write_text("value = 2\n")
    elif changed == "untracked":
        (root / "extra.py").write_text("value = 1\n")
    elif changed == "index":
        (root / "library.py").write_text("value = 2\n")
        subprocess.run(["git", "-C", str(root), "add", "library.py"], check=True)
        (root / "library.py").write_text("value = 1\n")
    elif changed == "origin":
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "remote",
                "set-url",
                "origin",
                "https://github.com/other/repo.git",
            ],
            check=True,
        )
    else:
        (root / ".governance").mkdir()
        (root / ".governance/standard-adoption.json").write_text("{}")
    with pytest.raises(ContractError, match="PLAN_STALE"):
        assert_repository_current(
            b["observation"], b["adoptions"], ctx["repository_roots"]
        )


def test_changed_classification_policy_is_stale_even_for_unused_pattern(selection):
    _, b, _, _, ctx = selection
    with pytest.raises(ContractError, match="policy|classification"):
        assert_repository_current(
            b["observation"],
            b["adoptions"],
            ctx["repository_roots"],
            inventory_options={"classification": {"generated": ["never/**"]}},
        )


def test_snapshot_artifact_bytes_are_checked_and_symlinks_refused(selection, tmp_path):
    _, b, _, _, ctx = selection
    artifacts = tmp_path / "reports"
    artifacts.mkdir()
    (artifacts / "inventory.json").write_bytes(canonical_bytes(b["inventory"]))
    (artifacts / "adoption.json").write_bytes(
        canonical_bytes(b["adoptions"]["owner/repo"])
    )
    assert_repository_current(
        b["observation"],
        b["adoptions"],
        ctx["repository_roots"],
        artifact_root=artifacts,
    )
    (artifacts / "inventory.json").write_text("{}")
    with pytest.raises(ContractError, match="evidence bytes"):
        assert_repository_current(
            b["observation"],
            b["adoptions"],
            ctx["repository_roots"],
            artifact_root=artifacts,
        )
    (artifacts / "inventory.json").unlink()
    (artifacts / "inventory.json").symlink_to(artifacts / "adoption.json")
    with pytest.raises(ContractError, match="Symlink"):
        assert_repository_current(
            b["observation"],
            b["adoptions"],
            ctx["repository_roots"],
            artifact_root=artifacts,
        )


def test_capture_detects_source_change_between_reads(selection, monkeypatch):
    root, _, _, _, _ = selection
    import wellman.selection_plan as module

    original = module.inventory_repository
    calls = []

    def changing(*args, **kwargs):
        if calls:
            (root / "library.py").write_text("value=99\n")
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "inventory_repository", changing)
    b = capture_repository(root)
    assert all(a["freshness"] == "stale" for a in b["observation"]["artifacts"])
    assert all(f["state"] == "unknown" for f in b["observation"]["features"])
    assert any(
        q["code"] == "SOURCE_CHANGED_DURING_SCAN"
        for q in b["observation"]["quality_issues"]
    )


def test_unknown_boundary_and_legacy_artifacts_defer(selection):
    _, b, c, _, _ = selection
    from wellman.applicability import catalog_digest

    c["standards"][0]["scope"] = "component"
    c["catalog_digest"] = catalog_digest(c)
    b["observation"]["components"][0]["boundary"] = "unknown"
    assert (
        decision(compose_selection_plan(b["observation"], c, b["adoptions"]))["action"]
        == "defer"
    )
    b["observation"]["components"][0]["boundary"] = "confirmed"
    for a in b["observation"]["artifacts"]:
        a["freshness"] = "legacy_unverified"
    assert (
        decision(compose_selection_plan(b["observation"], c, b["adoptions"]))["action"]
        == "defer"
    )


def test_self_declared_conformance_cannot_pass_live_export_check(selection):
    _, b, _, _, ctx = selection
    adoption = b["adoptions"]["owner/repo"]
    adoption["standards"][STANDARD]["conformance"] = "verified"
    adoption["adoption_digest"] = payload_digest(
        {k: v for k, v in adoption.items() if k != "adoption_digest"}
    )
    with pytest.raises(ContractError, match="adoption changed"):
        assert_repository_current(
            b["observation"], b["adoptions"], ctx["repository_roots"]
        )


def test_text_shows_reviewable_files_versions_risk_and_authority(selection):
    text = render_selection_plan(selection[3])
    for value in (
        "owner/repo",
        STANDARD,
        "AGENTS.md",
        PIN,
        "Risk:",
        "authorities:",
        "No execution authority",
    ):
        assert value in text
