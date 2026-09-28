# Ticket 015: support-remaining-fleet-docs-pins

- **ID**: ticket-015
- **Owner**: gemini
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-09-28

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: user requested execution of standardization fixes across fleet.
Add remaining published docs adoption pins to `SUPPORTED_DOCS_POLICIES` in `src/wellman/docs_adoption.py`:
- `0714f71462202788e6b775ed145e9e61a7d5c366` (`fac05e720ec49370ba393e817a4a03b895d7ed33828e09b3420f9fcfb09264b0`)
- `fdb0fcaa7c606dc2503cabb71eff64d5f86ee659` (`affe2ca5700b8225829d110ef704c793e280efae2349751ab7e3f3ef3303126e`)

## Acceptance criteria

- [x] AC-01: Both published adoption pins pass validator checks.
- [x] AC-02: `tests/test_validator.py` passes with parametrized test cases.
- [x] AC-03: `./project/governance-check.sh` passes cleanly (GOV-PASS).

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.

