# Ticket 090: register python standard pack in standards catalog

- **ID**: ticket-090
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-03

## Goal and scope

Register `wellmanifest/python` standard pack in `STANDARDS_CATALOG` (`src/wellman/registry.py`)
with its requirements, conformance specification, and documentation link.
Extend `tests/test_registry.py` to assert `wellmanifest/python` is discoverable and valid.

Scope: `src/wellman/registry.py`, `src/wellman/applicability.py`, `src/wellman/runner.py`, `src/wellman/schemas/standard-packs.json`, `tests/test_registry.py`.

## Acceptance criteria

- [x] AC-01: `wellmanifest/python` added to `STANDARDS_CATALOG` with `minimum_level="S0"`, `requires=["wellmanifest/semver"]`.
- [x] AC-02: `wellmanifest/python` registered in applicability `CAPABILITIES` as `language:python`, in runner standard checks, and in `standard-packs.json`.
- [x] AC-03: Tests in `tests/test_registry.py`, `tests/test_registry_dependencies.py`, and `tests/test_applicability.py` verify retrieval, schema SSOT, and dependency resolution for `wellmanifest/python`.
- [x] AC-04: `wellman check` and governance check pass cleanly.

## Evidence

- `tests/test_registry.py`: 7 passed in 0.15s.
- `tests/test_registry_dependencies.py`: 7 passed in 0.68s.
- `tests/test_applicability.py`: 102 passed.
- `tests/test_runner.py`: 27 passed.
- `./project/governance-check.sh`: GOV-PASS: passed (0 errors, 0 warnings).
- `wellman check`: 0 errors.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
