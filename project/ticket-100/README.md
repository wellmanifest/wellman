# Ticket 100: Implement S1 static checkers for remaining 14 catalog standards

- **ID**: ticket-100
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-10

## Goal and scope

Implement dependency-free, bounded, symlink-refusing `S1` static conformance checkers in `src/wellman/catalog_pack_checkers.py` and wire them into `ConformanceRunner` (`src/wellman/runner.py`) for all 14 remaining `STANDARDS_CATALOG` standards:

- `wellmanifest/authority-lifecycle`
- `wellmanifest/repair-lifecycle`
- `wellmanifest/account-runtime`
- `wellmanifest/skills`
- `wellmanifest/status`
- `wellmanifest/performance`
- `wellmanifest/llm`
- `wellmanifest/dsl`
- `wellmanifest/env-dsl`
- `wellmanifest/code-dsl`
- `wellmanifest/nl-dsl-llm`
- `wellmanifest/nl-api-llm`
- `wellmanifest/poa`
- `wellmanifest/anonym`

## Acceptance criteria

- [x] AC-01: Every standard in `STANDARDS_CATALOG` (`53/53`) executes a concrete deterministic `S1` static checker with positive, negative, and symlink-refusal test coverage, while unimplemented future IDs still fail closed with `GOV-STANDARD-NOT-IMPLEMENTED`.
- [x] AC-02: `./project/governance-check.sh` and `PYTHONPATH=src python3 -m wellman.cli check --root .` pass with zero errors.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
