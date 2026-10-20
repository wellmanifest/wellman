"""Tests for wellman.stream_flow and wellmanifest/modularity + wellmanifest/priority registration."""

from __future__ import annotations

import json
from pathlib import Path

from wellman.registry import STANDARDS_CATALOG, get_standard
from wellman.runner import ConformanceRunner
from wellman.stream_flow import (
    DecisionEngine,
    DecisionRule,
    DependencyResolver,
    PrioritizedDependency,
    StreamEnvelope,
    StreamPipeline,
    StreamStage,
    analyze_horizontal_complexity,
)


def test_registered_modularity_and_priority_standards() -> None:
    assert "wellmanifest/modularity" in STANDARDS_CATALOG
    assert "wellmanifest/priority" in STANDARDS_CATALOG
    assert get_standard("modularity").id == "wellmanifest/modularity"
    assert get_standard("priority").id == "wellmanifest/priority"
    reuse_std = get_standard("wellmanifest/reuse")
    assert "stream-flow.schema.json" in reuse_std.schemas


def test_decision_engine_and_dependency_resolver() -> None:
    engine = DecisionEngine(
        [
            DecisionRule(id="low", tier="opportunistic", weight=99.0, outcome="opt", when=lambda ctx: True),
            DecisionRule(id="high", tier="floor", weight=10.0, outcome="floor_win", when=lambda ctx: ctx.get("ok", False)),
        ],
        default_outcome="fallback",
    )
    verdict = engine.decide({"ok": True})
    assert verdict.selected_id == "high"
    assert verdict.outcome == "floor_win"

    resolver = DependencyResolver(
        [
            PrioritizedDependency(
                id="fast_native",
                capability="scanner",
                tier="floor",
                weight=100.0,
                provider=lambda: "native",
                readiness_probe=lambda: False,
                fallback_id="py_fallback",
            ),
            PrioritizedDependency(
                id="py_fallback",
                capability="scanner",
                tier="standard",
                weight=50.0,
                provider=lambda: "python",
                readiness_probe=lambda: True,
            ),
        ]
    )
    res = resolver.resolve("scanner")
    assert res.selected_id == "py_fallback"
    assert res.value == "python"


def test_stream_pipeline_and_horizontal_audit(tmp_path: Path) -> None:
    stages = [
        StreamStage(
            id="enrich",
            kind="component",
            tier="standard",
            weight=50.0,
            depends_on=("ingest",),
            transform=lambda env: env.payload * 2,
        ),
        StreamStage(
            id="ingest",
            kind="module",
            tier="floor",
            weight=100.0,
            transform=lambda env: env.payload + 1,
        ),
    ]
    pipeline = StreamPipeline("demo", stages)
    outputs = [env.payload for env in pipeline.stream([1, 2, 3])]
    assert outputs == [4, 6, 8]
    assert pipeline.last_receipt is not None
    assert pipeline.last_receipt.processed_count == 3
    assert pipeline.last_receipt.digest.startswith("sha256:")

    # Check horizontal audit on stream_flow.py itself
    stream_flow_dir = tmp_path / "clean_pkg"
    stream_flow_dir.mkdir()
    (stream_flow_dir / "mod.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    audit = analyze_horizontal_complexity(stream_flow_dir)
    assert audit["hotspot_count"] == 0


def test_runner_modularity_priority_and_stream_flow_check(tmp_path: Path) -> None:
    (tmp_path / "modularity.dsl").write_text("modularity demo version 0.1.0\nmodule core\n", encoding="utf-8")
    (tmp_path / "priority.dsl").write_text("priority_set demo version 0.1.0\npriority p1 tier floor\n", encoding="utf-8")
    runner = ConformanceRunner(tmp_path)
    assert runner.run_standard("wellmanifest/modularity") == []
    assert runner.run_standard("wellmanifest/priority") == []

    (tmp_path / ".reuse").mkdir()
    (tmp_path / ".reuse" / "redup-receipt.json").write_text(json.dumps({"findings": {"unmitigated": 0}}), encoding="utf-8")
    (tmp_path / ".reuse" / "stream-flow.json").write_text("{}", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("# Docs\n", encoding="utf-8")
    (tmp_path / "project" / "ticket-001").mkdir(parents=True)
    assert runner.run_standard("wellmanifest/reuse") == []


def test_runner_policy_and_lifecycle_dsl_checks(tmp_path: Path) -> None:
    assert "wellmanifest/lifecycle" in STANDARDS_CATALOG
    assert get_standard("lifecycle").id == "wellmanifest/lifecycle"
    assert get_standard("policy-dsl").id == "wellmanifest/policy-dsl"

    (tmp_path / "demo.policy").write_text(
        'DOCUMENT DEMO\nVERSION 1\nLANGUAGE EN\nMODE STRICT\nPURPOSE "demo"\nPOLICY "demo/v1"\n'
        "STATES [INIT, DONE]\n"
        "RULE R-001 TYPE REQUIRED\nWHEN READY\nDO ALLOW RUN\nASSERT VERIFIED\n"
        "TRANSITION [INIT] -> DONE WHEN READY\n",
        encoding="utf-8",
    )
    (tmp_path / "demo.lifecycle").write_text(
        'LIFECYCLE demo VERSION 1\nDESCRIPTION "demo"\n'
        "STATES [INIT] INITIAL\nSTATES [DONE] TERMINAL\n"
        "EVENTS [FINISH]\nEVIDENCES [PROOF]\n"
        "TRANSITION [INIT] -> DONE ON FINISH REQUIRES PROOF\nEND\n",
        encoding="utf-8",
    )
    runner = ConformanceRunner(tmp_path)
    assert runner.run_standard("wellmanifest/policy-dsl") == []
    assert runner.run_standard("wellmanifest/lifecycle") == []
    assert runner.run_standard("wellmanifest/legal-lifecycle") == []
    assert runner.run_standard("wellmanifest/product-lifecycle") == []
    assert runner.run_standard("wellmanifest/saas-lifecycle") == []
    assert runner.run_standard("wellmanifest/twin-lifecycle") == []
    assert runner.run_standard("wellmanifest/uriprocess") == []


def test_uri_function_and_cli_jsonl_pipeline(tmp_path: Path, capsys: object) -> None:
    from wellman import uri
    from wellman.uri import main as uri_main

    (tmp_path / "mod.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")

    # 1. Single invocation via uri('<full-uri>', dict)
    res = uri("proc://ast-scan/complexity/horizontal", {"root": str(tmp_path)})
    assert res["schema"] == "uriprocess.invocation-result/v1"
    assert res["ok"] is True
    assert res["uri"] == "proc://ast-scan/complexity/horizontal"
    assert res["result"]["hotspot_count"] == 0
    assert len(res["receipt"]["sha256"]) == 64

    # 2. Multi-line JSONL stream via uri('<full-uri>', jsonl_str, stream=True)
    jsonl_input = (
        json.dumps({"root": str(tmp_path), "max_branches": 4}) + "\n"
        + json.dumps({"root": str(tmp_path), "max_branches": 2}) + "\n"
    )
    batch = uri("proc://ast-scan/complexity/horizontal", jsonl_input, stream=True)
    assert isinstance(batch, list) and len(batch) == 2
    assert all(item["ok"] is True for item in batch)

    # 3. CLI `uri <address> <json>`
    rc = uri_main(["proc://ast-scan/complexity/horizontal", json.dumps({"root": str(tmp_path)})])
    assert rc == 0

    # 4. Polyglot uri('') link scanner catches invalid URI and accepts valid URI
    (tmp_path / "caller.sh").write_text(
        "#!/usr/bin/env bash\nuri 'proc://ast-scan/complexity/horizontal' '{\"root\":\".\"}'\n",
        encoding="utf-8",
    )
    scan_res = uri("proc://uriprocess/invocation/scan", {"root": str(tmp_path)})
    assert scan_res["result"]["valid_link_count"] == 1
    assert scan_res["result"]["invalid_link_count"] == 0


def test_uri_scanner_keeps_sources_under_ignored_ancestors(tmp_path):
    from wellman.uri import scan_uri_link_opportunities

    root = tmp_path / ".subactor/cache/checkout"
    root.mkdir(parents=True)
    (root / "caller.sh").write_text("uri 'proc://ast-scan/complexity/horizontal' '{}'\n")
    (root / "broken.py").write_text("uri('not-a-process-uri', {})\n")
    report = scan_uri_link_opportunities(root)
    assert report["valid_link_count"] == 1
    assert report["invalid_link_count"] == 1
    assert report["valid_links"][0]["path"] == "caller.sh"


def test_uri_scanner_prunes_ignored_trees_and_rejects_symlink_inputs(tmp_path, monkeypatch):
    import os
    from wellman.uri import scan_uri_link_opportunities

    root = tmp_path / "checkout"
    root.mkdir()
    ignored = root / ".venv"
    ignored.mkdir()
    (ignored / "ignored.sh").write_text("uri 'proc://ast-scan/complexity/horizontal' '{}'\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    source = outside / "foreign.sh"
    source.write_text("uri 'proc://ast-scan/complexity/horizontal' '{}'\n")
    (root / "linked.sh").symlink_to(source)
    (root / "linked-directory").symlink_to(outside, target_is_directory=True)
    walked = []
    real_walk = os.walk

    def observe_walk(*args, **kwargs):
        for item in real_walk(*args, **kwargs):
            walked.append(Path(item[0]))
            yield item

    monkeypatch.setattr(os, "walk", observe_walk)
    report = scan_uri_link_opportunities(root)
    assert report["valid_link_count"] == report["invalid_link_count"] == 0
    assert ignored not in walked and outside not in walked


