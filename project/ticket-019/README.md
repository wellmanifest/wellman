# Ticket 019: Support wellmanifest/docs 6f475fb in SUPPORTED_DOCS_POLICIES

- **ID**: ticket-019
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-09-29

## Goal and scope

Add upstream `wellmanifest/docs` 0.5.0 release revision `6f475fb223e7a259d514b5483fb0d62f0e80a46e`
to `SUPPORTED_DOCS_POLICIES` with its published policy digest `DOCS_POLICY_SHA256` so that
repositories adopting `wellmanifest/docs` via `standards-lock.json` are accepted without
`GOV-DOCS-DRIFT` error.

## Acceptance criteria

- [x] AC-01: Support revision `6f475fb223e7a259d514b5483fb0d62f0e80a46e` in `SUPPORTED_DOCS_POLICIES`.
- [x] AC-02: Unit test in `tests/test_validator.py` confirms `validate_docs` accepts `6f475fb` without `GOV-DOCS-DRIFT`.
- [x] AC-03: Governance check passes with 0 errors and 0 warnings.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
