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

Scope: `src/wellman/registry.py`, `tests/test_registry.py`.

## Acceptance criteria

- [x] AC-01: `wellmanifest/python` added to `STANDARDS_CATALOG` with `minimum_level="S0"`, `requires=["wellmanifest/semver"]`.
- [x] AC-02: Tests in `tests/test_registry.py` verify retrieval and dependency resolution for `wellmanifest/python`.
- [x] AC-03: `wellman check` and governance check pass cleanly.

## Evidence

- `tests/test_registry.py`: 7 passed in 0.15s.
- `./project/governance-check.sh`: GOV-PASS: passed (0 errors, 0 warnings).
- `wellman check`: 0 errors.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
