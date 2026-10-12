# Ticket 053: Fix active session WAL lock false positive in storage health check

- **ID**: ticket-053
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-12

## Goal and scope

Handle SQLite `OperationalError` during `_fallback_storage_health` check in `wellman.runner` when active agent sessions hold transient locks or WAL checkpoint locks on session databases, preventing false positive `GOV-SESSION-RECOVERY-001` corruption findings.

## Acceptance criteria

- [x] AC-01: `_fallback_storage_health` ignores transient SQLite operational errors (`database is locked`, `busy`, `unable to open database file`).
- [x] AC-02: Only genuine database corruption (failing `PRAGMA quick_check` or malformed disk image) raises `GOV-SESSION-RECOVERY-001`.
- [x] AC-03: Conformance tests and regression test added in `tests/test_session_recovery.py`.
- [x] AC-04: Full test suite and governance checks pass with 0 errors and 0 warnings.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
