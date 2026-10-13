# Ticket 055: implement reuse conformance check in wellman runner

- **ID**: ticket-055
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-13

## Goal and scope

Implement `wellmanifest/reuse` standard conformance checker in wellman runner, enabling concrete policy enforcement for clone receipts, planfiles, and docs.

## Acceptance criteria

- [x] AC-01: Implement `check_reuse` in `ConformanceRunner` in `wellman/runner.py`.
- [x] AC-02: Register `wellmanifest/reuse` conformance check in `run_standard` and `run_all`.
- [x] AC-03: Add unit tests in `tests/test_runner.py` with 100% pass rate.
- [x] AC-04: Governance check passes cleanly with 0 errors, 0 warnings.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
