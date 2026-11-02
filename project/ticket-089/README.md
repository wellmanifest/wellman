# Ticket 089: wire-nohardcode-ssot-and-fleet-freshness-update

- **ID**: ticket-089
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-02

## Goal and scope

Enhance Wellman runner and fleet synchronization to:
1. Wire `wellmanifest/nohardcode` and `wellmanifest/ssot` into `ConformanceRunner.run_all()` with detection for unauthorized path leaks (`~/.local/state`, `/tmp`) outside the repository.
2. Upgrade `fleet.sync_agent_instructions` to support updating existing agent files when content differs and automatically enforce local Git hooks (`core.hooksPath .githooks`).
3. Refresh `_bundled/create_adoption_lock.py` to match the latest `wellmanifest/new-project` release.
4. Update supported documentation adoption policies in `docs_adoption.py`.

## Acceptance criteria

- [x] AC-01: `ConformanceRunner` includes `check_nohardcode` and `check_ssot` validations.
- [x] AC-02: `check_nohardcode` detects machine-local path leaks (`~/.local/state`, `/tmp`) violating wellmanifest path confinement.
- [x] AC-03: `sync_agent_instructions` supports overwrite/update when existing instruction files differ and configures `core.hooksPath .githooks`.
- [x] AC-04: Bundled `create_adoption_lock.py` is synchronized with `wellmanifest/new-project`.
- [x] AC-05: All unit and conformance tests pass.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
