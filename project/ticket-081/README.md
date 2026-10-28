# Ticket 081: Admit flowguard bounded concurrency and heyasa multi-task dependency gates

- **ID**: ticket-081
- **Owner**: subactor/coding-agent
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-28

## Goal and scope

Admit `wellmanifest/flowguard` as a registered Wellmanifest standard and implement its conformance check in `wellman`. This ensures repositories utilizing Heyasa concurrent task dispatch adhere to bounded resource limits, DAG dependency isolation, and Head-of-Line decongestion rules.

## Acceptance criteria

- [x] AC-01: Register `wellmanifest/flowguard` standard pack in `src/wellman/registry.py` with alias and S3 minimum level.
- [x] AC-02: Implement `check_flowguard` in `src/wellman/runner.py` verifying flowguard integration and detecting unbounded blocking subprocess calls.
- [x] AC-03: Wire `check_flowguard` into `run_standard` and `run_all`.
- [x] AC-04: Unit tests in `tests/test_flowguard_gate.py` pass 100%.
- [x] AC-05: Conformance passes via `./project/governance-check.sh` and `wellman check`.
- [x] AC-06: Register capability `runtime:flow-guard` in `src/wellman/applicability.py`.
- [x] AC-07: Synchronize `src/wellman/schemas/standard-packs.json` with flowguard standard pack ownership.
