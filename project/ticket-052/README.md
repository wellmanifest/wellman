# Ticket 052: integrate uncrash session recovery diagnostics in wellman

- **ID**: ticket-052
- **Owner**: agent:gemini
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-10

## Goal and scope

Integrate `semcod/uncrash` session recovery diagnostics and `wellmanifest/session-recovery` conformance checks into `wellman`. Provide proactive detection of corrupted coding agent session databases and unhandled runtime panics during governance checks.

## Acceptance criteria

- [x] AC-01: Register `wellmanifest/session-recovery` standard pack and `agent-executor` profile mapping in `wellman.registry`.
- [x] AC-02: Map `session-recovery` capability in `wellman.applicability`.
- [x] AC-03: Implement `check_session_recovery` in `ConformanceRunner` delegating to `uncrash.diagnostics.check_agent_storage_health` with standalone fallback.
- [x] AC-04: Detect corrupted SQLite session databases (`GOV-SESSION-RECOVERY-001`), unhandled panics (`GOV-SESSION-RECOVERY-002`), and missing adoption lockfile (`GOV-SESSION-RECOVERY-LOCK`).
- [x] AC-05: Unit tests in `tests/test_session_recovery.py` pass.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
