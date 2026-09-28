# Ticket 013: Register wellmanifest/nl-api-llm standard pack in fleet catalog

- **ID**: ticket-013
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-09-28

## Goal and scope

1. Register `wellmanifest/nl-api-llm` in `src/wellman/schemas/standard-packs.json` standard pack catalog.
2. Register `wellmanifest/nl-api-llm` in `STANDARDS_CATALOG` in `src/wellman/registry.py` with minimum level S4 and protected-conformance model.
3. Add aliases (`nl-api`, `nl-api-llm`, `nl-dsl`, `nl-dsl-llm`) in `get_standard`.
4. Add conformance test verification in `tests/test_registry.py`.

## Acceptance criteria

- [x] AC-01: `wellmanifest/nl-api-llm` is present in `standard-packs.json` and `STANDARDS_CATALOG`.
- [x] AC-02: `get_standard("nl-api-llm")` resolves correctly.
- [x] AC-03: `tests/test_registry.py` passes with new assertions.
- [x] AC-04: `./project/governance-check.sh` passes cleanly (GOV-PASS).

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
