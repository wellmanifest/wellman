# Ticket 082: Register data-plane standard and complete conformance checker mappings

- **ID**: ticket-082
- **Owner**: gemini
- **Status**: IN_PROGRESS
- **Workflow state**: VALIDATION
- **Created**: 2026-10-30

## Goal and scope

Register `wellmanifest/data-plane` in `STANDARDS_CATALOG` and standard aliases, and complete the standard-specific conformance checker mappings in `ConformanceRunner` for `data-plane`, `taskand`, `deployment`, and `semver`.

## Acceptance criteria

- [x] AC-01: `wellmanifest/data-plane` standard is registered in `STANDARDS_CATALOG` with schemas and minimum level S3.
- [x] AC-02: `data-plane` and `taskand` conformance checkers (`check_data_plane`, `check_taskand`) implemented in `ConformanceRunner`.
- [x] AC-03: `check_selected_standard` maps `deployment`, `semver`, `taskand`, and `data-plane` to prevent `GOV-STANDARD-NOT-IMPLEMENTED` false failures.
- [x] AC-04: Unit tests in `tests/test_runner.py` verify positive, negative, and registration behaviors.

## Delivery status

Delivered runtime implementations in `src/wellman/registry.py` and `src/wellman/runner.py`, verified with unit test suite in `tests/test_runner.py`.
