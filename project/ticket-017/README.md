# Ticket 017: support taskand executor in fleet tickets

- **ID**: ticket-017
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-09-28

## Goal and scope

Support `taskand` as an autonomous executor alongside `koru` in `wellman fleet check`:
- Add `--taskand-handoff` and `--taskand-exec` CLI flags to `wellman fleet check`.
- Emit typed operations metadata (`taskand` field with `artifact.update`, `git.commit`, `ci.status`) and `executor_kind: taskand`.
- Provide `trigger_taskand_execution` runner for autonomous remediation via taskand.

## Acceptance criteria

- [x] AC-01: `emit_standardization_tickets` supports `taskand_ready=True` setting `executor_kind: taskand`, `taskand-refactor` and `taskand-job` labels, and structured typed operations.
- [x] AC-02: `wellman fleet check` exposes `--taskand-handoff` and `--taskand-exec` CLI flags.
- [x] AC-03: `trigger_taskand_execution` safely runs standardization adoption, checks, and Git commits with clean receipts.
- [x] AC-04: Pytest suite passes all 127 tests cleanly.
- [x] AC-05: `./project/governance-check.sh` passes with 0 errors and 0 warnings.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
