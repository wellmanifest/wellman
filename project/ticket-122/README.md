# Ticket 122: Auto-sync LLM host standards SSOT on wellman version bump

- **ID**: ticket-122
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-23

## Goal and scope

Add `maybe_auto_sync_host_agents()` in `src/wellman/host_agent_sync.py` and invoke it automatically in `src/wellman/__main__.py` so that whenever `wellman` upgrades to a new version, the next `python -m wellman ...` invocation automatically refreshes `STANDARDS.md`, `AGENT-INVARIANTS.md`, and all non-git LLM host/workspace instruction files while safely skipping CI, pytest, opt-out (`WELLMAN_NO_AUTO_HOST_SYNC=1`), and hosts without a local `wellmanifest` workspace.

Execution authorization: `SESSION_EXECUTION_AUTHORIZATION` granted by direct user request ("on powinien to robic automatycznie na wszytskich po kazdym zwiekszeniu wersji").

## Acceptance criteria

- [x] AC-01: `maybe_auto_sync_host_agents()` returns `None` in CI (`CI`, `GITHUB_ACTIONS`), `PYTEST_CURRENT_TEST`, `WELLMAN_NO_AUTO_HOST_SYNC=1`, or when `wellmanifest_root` is absent.
- [x] AC-02: `maybe_auto_sync_host_agents()` automatically re-syncs all non-git LLM host configs on a `wellman` version bump and skips in O(1) when already synced.
- [x] AC-03: `src/wellman/__main__.py` invokes `maybe_auto_sync_host_agents()` automatically before dispatching subcommands.
- [x] AC-04: `tests/test_host_agent_sync.py` covers CI/opt-out guards, no-op on matching version, and automatic re-sync on version bump.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
