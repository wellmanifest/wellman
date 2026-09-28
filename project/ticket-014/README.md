# Ticket 014: support-legacy-docs-and-plf-branches

- **ID**: ticket-014
- **Owner**: gemini
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-09-28

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: user requested investigation and remediation of Wellman and fleet standardization.
1. Add legacy published Docs adoption pins (`ebe7501063ef4f3e63ded610c2d3183010ca636e` and `9fb5fc4d99afb70ca577b84b0bf115e52e43a1c6`) to `SUPPORTED_DOCS_POLICIES` in `src/wellman/docs_adoption.py` to recognize valid fleet adoptions without false-positive drift warnings.
2. Extend branch naming regex pattern in `src/wellman/runner.py` to accept `ticket/PLF-\d+` branches conforming with Planfile ticket lifecycles.
3. Add unit test coverage in `tests/test_validator.py` and `tests/test_runner.py`.

## Acceptance criteria

- [x] AC-01: Legacy published docs adoption pins are supported in `SUPPORTED_DOCS_POLICIES` and verified in tests.
- [x] AC-02: `ticket/PLF-*` branches are recognized by `ConformanceRunner.check_git_lifecycle()`.
- [x] AC-03: Full test suite passes.
- [x] AC-04: `./project/governance-check.sh` passes cleanly (GOV-PASS).

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.

