# Ticket 078: Fix check_mcp worktree relative path and support dockuri procedures dict

- **ID**: ticket-078
- **Owner**: agent:gemini
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-27

SESSION_EXECUTION_AUTHORIZATION: user requested piloting standards validation on `autogrammar/edialog` and fixing any anomalies discovered before fleet rollout.

## Goal and scope

1. Use `p.relative_to(self.root).parts` in `check_mcp()` and `check_hostguard()` so running `wellman check` inside `.worktrees/ticket-NNN--slug` does not falsely exclude files inside the worktree.
2. Support `procedures` dict in `dockuri.json` (`check_dockuri()`), in addition to `processes` list.
3. Add domain/NL/DSL standard checks (`check_dsl`, `check_llm`, `check_nl_contracts`) and register them in `checked` and `run_standard()` so repositories adopting `domain-pack` and `nl-*` standards validate cleanly.

## Acceptance criteria

- [x] AC-01: `check_mcp()` and `check_hostguard()` succeed when `self.root` is inside `.worktrees/ticket-NNN--slug`.
- [x] AC-02: `check_dockuri()` extracts URIs from both `procedures` (mapping) and `processes` (list) in `dockuri.json`.
- [x] AC-03: Unit tests in `tests/test_registry_dependencies.py` and `./project/governance-check.sh` pass.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
