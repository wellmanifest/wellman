# Ticket 123: Normalize wellmanifest/ prefix in host_agent_sync collect_standards to eliminate duplicate and broken URLs

- **ID**: ticket-123
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-23

## Goal and scope

Normalize `wellmanifest/` prefixes returned by `wellman.registry.list_standards()` inside `collect_standards()` in `src/wellman/host_agent_sync.py` so registry standards merge cleanly with `repos.manifest` entries without producing duplicate rows or broken `https://github.com/wellmanifest/wellmanifest/<name>` URLs.

Execution authorization: `SESSION_EXECUTION_AUTHORIZATION` granted by direct user confirmation ("tak").

## Acceptance criteria

- [x] AC-01: `_normalize_standard_name()` strips leading `wellmanifest/` prefixes before indexing in `collect_standards()`.
- [x] AC-02: `STANDARDS.md` contains zero `wellmanifest/wellmanifest/` URLs and zero duplicate rows between `wellman.registry` and `repos.manifest`.
- [x] AC-03: `tests/test_host_agent_sync.py` asserts absence of `wellmanifest/wellmanifest/` and `**wellmanifest/worktrees**`.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
