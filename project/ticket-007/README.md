# Ticket 007: Add contextual auto-discovery for multi-repo hierarchies and agent host standard projection

- **ID**: ticket-007
- **Owner**: antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-09-24

## Goal and scope

1. **Contextual auto-discovery in `discover_repositories`**:
   - When executed in an umbrella / organization root (where direct children are not git repositories but sub-directories contain repositories), automatically discover nested repositories without requiring an explicit `--recursive` flag.
   - Support explicit `--no-recursive` when strictly direct children are required.
2. **Agent host standard projection**:
   - Provide `sync_agent_instructions` in `wellman.fleet` to project and synchronize standard instruction contracts for any registered LLM agent host (`AGENTS.md`, `GEMINI.md`, `CLAUDE.md`, `.cursor/rules/`, `.github/copilot-instructions.md`, `.aider.conf.yml`).
   - Wire `sync-agents` action and `--sync-agents` flag into `wellman fleet adopt` and `wellman fleet sync-agents`.
3. Add unit tests in `tests/test_fleet.py` verifying both contextual auto-discovery and agent host standard projection.

## Acceptance criteria

- [x] AC-01: `discover_repositories` auto-discovers nested repos in organization/multi-repo hierarchies when direct repos are 0.
- [x] AC-02: `sync_agent_instructions` generates valid instruction files for all registered agent hosts.
- [x] AC-03: `wellman fleet` commands support automatic hierarchical discovery.
- [x] AC-04: All test suites (`pytest`) and governance checks pass.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.

