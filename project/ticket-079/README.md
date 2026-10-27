# Ticket 079: Auto-expand transitive standard dependencies in adoption.register

- **ID**: ticket-079
- **Owner**: agent:gemini (`SESSION_EXECUTION_AUTHORIZATION`)
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-27

## Goal and scope

Automatically expand transitive standard dependencies (`expand_standard_dependencies`) inside `wellman.adoption.register()` so that every `wellman adopt` and `wellman fleet adopt` invocation writes a dependency-complete `.governance/standard-requirements.json` that passes `STD-DEP-MISSING` validation.

## Acceptance criteria

- [x] AC-01: `wellman.adoption.register()` expands transitive standard dependencies from `StandardPack.requires`.
- [x] AC-02: Existing and new unit tests pass (`pytest -q`).

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
