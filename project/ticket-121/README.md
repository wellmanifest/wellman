# Ticket 121: Add version-stamped host_agent_sync module for LLM host standards SSOT

- **ID**: ticket-121
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-23

## Goal and scope

Add `src/wellman/host_agent_sync.py` and wire `python -m wellman sync-hosts` in `src/wellman/__main__.py` so that `wellman` itself generates and updates the live unpinned `STANDARDS.md`, `AGENT-INVARIANTS.md`, and version-stamped `<!-- wellmanifest:standards-ssot:start wellman-version=... -->` blocks across all non-git LLM host/IDE configs (Claude, Codex, Gemini, Cursor, OpenCode, Windsurf, Copilot, Droid, Continue, Cline, Aider) and workspace `AGENTS.md` files whenever a new `wellman` version is released.

Execution authorization: `SESSION_EXECUTION_AUTHORIZATION` granted by direct user request ("tak na prawde te reguly nie powinny byc teraz recznie tworzone tylko aktualizowane przez wellmanifest/wellman, za kazdym razem jak pojawia sie nowa wersja wellman").

## Acceptance criteria

- [x] AC-01: `src/wellman/host_agent_sync.py` generates `STANDARDS.md` and `AGENT-INVARIANTS.md` from `wellman.registry` + optional `repos.manifest` with hard `.worktrees/` / `.subactor/recovery/` invariants and zero pinned standard SHAs.
- [x] AC-02: `sync_host_agents(..., if_version_changed=True)` detects `wellman-version=<ver>` in managed blocks, skips when up-to-date, and re-syncs all non-git LLM host configs automatically on a `wellman` version bump while skipping git-tracked directories (`SKIP_GIT`).
- [x] AC-03: `python -m wellman sync-hosts` (via `src/wellman/__main__.py`) supports `--if-version-changed`, `--check`, and `--json`.
- [x] AC-04: `tests/test_host_agent_sync.py` verifies generation, preservation of existing host rules, git-skip safety, version-bump auto-resync, and `--check` drift exit codes using `tmp_path`.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
