# Ticket 077: Add standard pack dependency graph, sync schemas, and enforce dockuri/report checks

- **ID**: ticket-077
- **Owner**: agent:gemini
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-27

SESSION_EXECUTION_AUTHORIZATION: user requested cross-standard dependency validation, SSoT schema deduplication, and dockuri/report conformance checks before pilot verification in `autogrammar/edialog`.

## Goal and scope

1. Add `requires` dependency graph to `StandardPack` in `src/wellman/registry.py`, register missing standards (`wellmanifest/dockuri`, `wellmanifest/report`, `wellmanifest/project-ssot`, `wellmanifest/env-dsl`, `wellmanifest/status`, `wellmanifest/performance`), and provide `expand_standard_dependencies()` and `missing_standard_dependencies()`.
2. Synchronize `src/wellman/schemas/standard-packs.json` and drifted schemas in `src/wellman/schemas/` with canonical `wellmanifest/new-project` and `wellmanifest/merge` definitions.
3. Validate profile completeness (`STD-PROFILE-REQ-MISSING`) and standard dependency completeness (`STD-DEP-MISSING`) in `StandardsValidator.validate_standard_dependencies()`.
4. Add `check_dockuri()` (including `dockuri.json` / `dockuri.yaml` / `uriprocess.json` URI parity verification) and `check_report()` in `src/wellman/runner.py`.

## Acceptance criteria

- [x] AC-01: `StandardPack.requires`, `expand_standard_dependencies()`, and `missing_standard_dependencies()` work deterministically with zero dependency cycles.
- [x] AC-02: `src/wellman/schemas/standard-packs.json` and bundled schemas are synchronized with canonical sources.
- [x] AC-03: `StandardsValidator.validate_standard_dependencies()` and `ConformanceRunner.check_dockuri()` / `check_report()` detect missing dependencies and URI manifest drift.
- [x] AC-04: Full `pytest` suite and `./project/governance-check.sh` pass with 0 errors and 0 warnings.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
