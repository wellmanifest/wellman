# Ticket 094: support wellmanifest/docs 0.6.0 pin in SUPPORTED_DOCS_POLICIES

- **ID**: ticket-094
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-10

## Goal and scope

Add upstream `wellmanifest/docs` 0.6.0 release revision `b536d012cde20a27fbc9ff2b3dfc8c80bfc075a0`
to `SUPPORTED_DOCS_POLICIES` with its published policy digest `fac05e720ec49370ba393e817a4a03b895d7ed33828e09b3420f9fcfb09264b0` so that
repositories adopting `wellmanifest/docs` 0.6.0 (such as `maskservice/c2004`) are accepted without
`GOV-DOCS-DRIFT` error.

## Acceptance criteria

- [x] AC-01: Support revision `b536d012cde20a27fbc9ff2b3dfc8c80bfc075a0` in `SUPPORTED_DOCS_POLICIES`.
- [x] AC-02: Unit test in `tests/test_validator.py` confirms `validate_docs` accepts `b536d012` without `GOV-DOCS-DRIFT`.
- [x] AC-03: Governance check passes with 0 errors and 0 warnings.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
