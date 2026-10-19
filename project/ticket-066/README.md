# Ticket 066: Integrate stream_flow engine and register modularity, priority, policy-dsl, and lifecycle standards

- **ID**: ticket-066
- **Owner**: antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-19

## Goal and scope

Integrate the `stream_flow` engine (`DecisionEngine`, `DependencyResolver`, `StreamPipeline`, and `analyze_horizontal_complexity`) into `wellman`, register `wellmanifest/modularity`, `wellmanifest/priority`, and `wellmanifest/lifecycle` in `STANDARDS_CATALOG`, bundle the latest `policy_dsl_check.py` (`7855f21`) and `lifecycle.py` (`1ea2a90`) validators into `src/wellman/_bundled/`, and wire executable conformance and compaction checks for `wellmanifest/policy-dsl`, `wellmanifest/lifecycle`, and domain `wellmanifest/*-lifecycle` standards in `ConformanceRunner` and `StandardsValidator`.

## Acceptance criteria

- [x] AC-01: `src/wellman/stream_flow.py` implements `DecisionEngine`, `DependencyResolver`, `StreamPipeline`, and `analyze_horizontal_complexity` (REUSE-015..018), and `src/wellman/applicability.py` replaces its 5-arm adoption branch chain with `_apply_adoption_transition`.
- [x] AC-02: `wellmanifest/modularity`, `wellmanifest/priority`, and `wellmanifest/lifecycle` are registered in `STANDARDS_CATALOG`, `StandardsValidator`, and `ConformanceRunner`.
- [x] AC-03: Bundled `policy_dsl_check.py` and `lifecycle.py` validate and audit `.policy` and `.lifecycle` files via `ConformanceRunner.check_policy_dsl()` and `ConformanceRunner.check_lifecycle_dsl()`.
- [x] AC-04: `src/wellman/uri.py` provides universal `uri('<address>', payload)` and `wellman uri <address> '<jsonl>'` JSONL invocation backed by `StreamPipeline` and `DependencyResolver` (`floor:in_process_registry` -> `standard:dockuri_router` -> `standard:dockuri_cli_jsonl`), plus `ConformanceRunner.check_uriprocess()`.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
