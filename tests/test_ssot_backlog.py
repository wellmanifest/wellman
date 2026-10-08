import subprocess
from copy import deepcopy

import pytest

from wellman.selection_contracts import canonical_bytes, payload_digest
from wellman.selection_plan import capture_repository
from wellman.ssot_backlog import export_ssot_backlog

pytest.importorskip("planfile.core.store")


def fixture(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    for args in (
        ["init", "-q"],
        ["remote", "add", "origin", "https://github.com/acme/library.git"],
    ):
        subprocess.run(["git", "-C", str(source), *args], check=True)
    (source / "pyproject.toml").write_text(
        '[project]\nname="library"\nversion="1.0.0"\n'
    )
    (source / "library.py").write_text("VALUE = 1\n")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=t@example.invalid",
            "commit",
            "-qm",
            "Fixture",
        ],
        check=True,
    )
    bundle = capture_repository(source)
    observation = bundle["observation"]
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "inventory.json").write_bytes(canonical_bytes(bundle["inventory"]))
    (artifacts / "adoption.json").write_bytes(
        canonical_bytes(bundle["adoptions"]["acme/library"])
    )
    component = observation["components"][0]["id"]
    owner = {
        "id": "owner",
        "domain": "billing",
        "kind": "rule",
        "key": "quota",
        "component_id": component,
        "role": "owner",
        "content_digest": "6" * 64,
        "evidence_refs": ["inventory"],
        "source_id": None,
        "source_digest": None,
    }
    declarations = {
        "schema": "wellman.ssot-declarations/v1",
        "observation_digest": payload_digest(observation),
        "records": [owner, {**owner, "id": "other"}],
    }
    context = {
        "repository_roots": {"acme/library": source},
        "adoptions": bundle["adoptions"],
        "artifact_root": artifacts,
    }
    target = tmp_path / "backlog"
    target.mkdir()
    return source, observation, declarations, target, context


def export(data):
    _, obs, decl, target, context = data
    return export_ssot_backlog(obs, decl, target, context=context)


def store(data):
    return pytest.importorskip("planfile.core.store").Store(data[3])


def test_export_creates_only_human_review_preserving_inputs_and_source(tmp_path):
    data = fixture(tmp_path)
    snapshot = deepcopy(data[1:3])
    before = {
        str(p.relative_to(data[0])): p.read_bytes()
        for p in data[0].rglob("*")
        if p.is_file()
    }
    receipt = export(data)
    assert receipt["ok"], receipt
    assert receipt["created"] == receipt["count"] == 1
    assert receipt["schema"] == "wellman.ssot-backlog-receipt/v1"
    assert (
        not receipt["remote_effects"]
        and not receipt["executable"]
        and not receipt["grants_authority"]
    )
    t = store(data).get_ticket(receipt["tickets"][0]["id"])
    assert (
        t.id.startswith("PLF-") and t.status.value == "open" and t.sprint == "backlog"
    )
    assert (t.executor.kind, t.executor.mode) == ("human", "interactive")
    assert t.execution.state == "pending" and t.execution.queue == "wellman-ssot-review"
    assert t.inputs is None and not t.source.context["proposal"]["executable"]
    assert t.source.context["observation_digest"] == payload_digest(data[1])
    assert (
        "behavior-preservation tests"
        in t.source.context["proposal"]["required_validation"]
    )
    assert data[1:3] == snapshot
    assert {
        str(p.relative_to(data[0])): p.read_bytes()
        for p in data[0].rglob("*")
        if p.is_file()
    } == before
    assert not (data[3] / ".planfile/sync").exists()


def test_dedupe_is_idempotent_and_refreshes_evidence_only(tmp_path):
    data = fixture(tmp_path)
    first = export(data)
    native = store(data)
    t = native.get_ticket(first["tickets"][0]["id"])
    original = t.model_dump(mode="json")
    assert export(data)["tickets"][0]["state"] == "reused"
    assert native.get_ticket(t.id).model_dump(mode="json") == original
    data[2]["records"][0]["content_digest"] = "7" * 64
    newer = export(data)
    assert newer["created"] == 0 and newer["tickets"][0]["state"] == "updated"
    refreshed = native.get_ticket(t.id)
    assert refreshed.updated_at > t.updated_at
    assert newer["analysis_digest"] != first["analysis_digest"]
    assert refreshed.executor == t.executor and refreshed.execution == t.execution


@pytest.mark.parametrize("terminal", ["done", "canceled", "failed", "blocked"])
def test_completed_or_blocked_proposals_are_never_reopened(tmp_path, terminal):
    data = fixture(tmp_path)
    receipt = export(data)
    native = store(data)
    t = native.get_ticket(receipt["tickets"][0]["id"])
    t = native.update_ticket(
        t.id, status=terminal, expected_updated_at=t.updated_at.isoformat()
    )
    before = t.model_dump(mode="json")
    data[2]["records"][0]["content_digest"] = "8" * 64
    assert export(data)["tickets"][0]["state"] == "preserved_terminal"
    assert native.get_ticket(t.id).model_dump(mode="json") == before


@pytest.mark.parametrize(
    "change",
    [
        {"status": "active"},
        {"sprint": "current"},
        {"blocked_by": ["PLF-999"]},
        {"executor": {"kind": "shell", "command": "true"}},
        {"execution": {"state": "pending", "queue": "elsewhere"}},
        {
            "execution": {
                "state": "pending",
                "queue": "wellman-ssot-review",
                "assigned_to": "reviewer",
            }
        },
        {"labels": ["reviewer-owned"]},
    ],
)
def test_foreign_owned_records_are_preserved(tmp_path, change):
    data = fixture(tmp_path)
    receipt = export(data)
    native = store(data)
    t = native.get_ticket(receipt["tickets"][0]["id"])
    # Keep the dedupe label so export can observe ownership rather than create another task.
    if "labels" in change:
        change = {
            "labels": change["labels"]
            + [l for l in t.labels if l.startswith("dedupe:")]
        }
    updated = native.update_ticket(
        t.id, expected_updated_at=t.updated_at.isoformat(), **change
    )
    before = updated.model_dump(mode="json")
    data[2]["records"][0]["content_digest"] = "8" * 64
    assert export(data)["tickets"][0]["state"] == "preserved_owned"
    assert native.get_ticket(t.id).model_dump(mode="json") == before


@pytest.mark.parametrize("change", ["source", "index", "artifacts", "observation"])
def test_drift_is_rejected_before_any_backlog_write(tmp_path, change):
    data = fixture(tmp_path)
    if change == "source":
        (data[0] / "library.py").write_text("VALUE = 2\n")
    elif change == "index":
        (data[0] / "library.py").write_text("VALUE = 2\n")
        subprocess.run(["git", "-C", str(data[0]), "add", "."], check=True)
    elif change == "artifacts":
        (data[4]["artifact_root"] / "inventory.json").write_text("{}")
    else:
        data[1]["observation_id"] = "different"
    assert not export(data)["ok"]
    assert not (data[3] / ".planfile").exists()


@pytest.mark.parametrize(
    "unsafe", ["source", "ancestor", "artifacts", "symlink", "storage-link"]
)
def test_storage_boundary_refuses_sources_artifacts_and_symlinks(tmp_path, unsafe):
    source, obs, decl, target, context = fixture(tmp_path)
    if unsafe == "source":
        target = source / "backlog"
    elif unsafe == "ancestor":
        target = tmp_path
    elif unsafe == "artifacts":
        target = context["artifact_root"] / "backlog"
    elif unsafe == "symlink":
        target = tmp_path / "link"
        target.symlink_to(tmp_path / "backlog", target_is_directory=True)
    else:
        (target / ".planfile").symlink_to(source, target_is_directory=True)
    assert not export_ssot_backlog(obs, decl, target, context=context)["ok"]
    assert not (source / ".planfile").exists()


def test_deferred_and_empty_findings_do_not_create_tasks(tmp_path):
    data = fixture(tmp_path)
    data[1]["quality_issues"].append(
        {
            "code": "BAD_GRAPH",
            "severity": "error",
            "message": "Invalid graph",
            "affected_refs": ["inventory-stage"],
            "next_action": "Rescan",
        }
    )
    data[2]["observation_digest"] = payload_digest(data[1])
    receipt = export(data)
    assert receipt["ok"] and receipt["deferred"] == 1 and receipt["count"] == 0
    assert not (data[3] / ".planfile").exists()
    data[2]["records"] = []
    assert export(data)["count"] == 0


def test_invalid_optional_adapter_and_missing_context_fail_without_write(
    tmp_path, monkeypatch
):
    data = fixture(tmp_path)
    import planfile

    monkeypatch.setattr(planfile, "__version__", "unknown")
    assert not export(data)["ok"]
    assert not export_ssot_backlog(data[1], data[2], data[3], context=None)["ok"]
    data[4].pop("artifact_root")
    assert not export(data)["ok"]
    assert not (data[3] / ".planfile").exists()


def test_source_revalidated_after_lock_wait(tmp_path, monkeypatch):
    from contextlib import contextmanager

    data = fixture(tmp_path)
    Store = pytest.importorskip("planfile.core.store").Store
    lock = Store.mutation_lock

    @contextmanager
    def changed(self, *args, **kwargs):
        with lock(self, *args, **kwargs):
            (data[0] / "library.py").write_text("VALUE = 3\n")
            yield

    monkeypatch.setattr(Store, "mutation_lock", changed)
    receipt = export(data)
    assert not receipt["ok"] and "PLAN_STALE" in receipt["error"]
    assert list(store(data).ticket_records(sprint="all")) == []


def test_each_invalid_consumer_has_a_distinct_review_identity(tmp_path):
    data = fixture(tmp_path)
    owner = data[2]["records"][0]
    data[2]["records"] = [
        owner,
        *[
            {**owner, "id": id, "role": "consumer", "source_id": "missing"}
            for id in ("one", "two")
        ],
    ]
    receipt = export(data)
    assert receipt["ok"] and receipt["created"] == 2
    assert len({r["key"] for r in receipt["tickets"]}) == 2


def test_parallel_exports_allocate_only_one_task(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    data = fixture(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: export(data), range(2)))
    assert all(r["ok"] for r in results), results
    assert sum(r["created"] for r in results) == 1
    assert len(list(store(data).ticket_records(sprint="all"))) == 1


def test_ambiguous_existing_keys_are_refused_without_creating_more_tasks(tmp_path):
    data = fixture(tmp_path)
    first = export(data)
    native = store(data)
    original = native.get_ticket(first["tickets"][0]["id"])
    from planfile.core.models import Ticket

    with native.mutation_lock():
        copy = Ticket(
            **{**original.model_dump(mode="json"), "id": native._next_id_unlocked()}
        )
        native._create_ticket_unlocked(copy)
    before = [t.model_dump(mode="json") for t in native.list_tickets(sprint="all")]
    receipt = export(data)
    assert not receipt["ok"] and "Ambiguous existing" in receipt["error"]
    assert [
        t.model_dump(mode="json") for t in native.list_tickets(sprint="all")
    ] == before


@pytest.mark.parametrize(
    "field", ["repository_roots", "adoptions", "inventory_options"]
)
def test_invalid_context_is_a_bounded_failure(tmp_path, field):
    data = fixture(tmp_path)
    data[4][field] = ["invalid"]
    assert not export(data)["ok"]
    assert not (data[3] / ".planfile").exists()
