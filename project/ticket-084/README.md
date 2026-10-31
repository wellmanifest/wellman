# Ticket 084: Restore applicability for data-plane

- **ID**: ticket-084
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-10-31

## Goal and scope

Restore imports of applicability after the data-plane catalog entry was added without a corresponding feature mapping. Preserve the declarative selection and no-authority boundary.

## Acceptance criteria

- [x] AC-01: Every registered non-baseline standard has a capability rule and the complete test suite collects.

## Session authorization

SESSION_EXECUTION_AUTHORIZATION: user requested continuation and protected merge of Wellman work; this regression blocks its validation. Publication authorized through protected controller and independent Validator only.

## Validation

95 applicability tests passed. Managed governance passed. Full-suite run started successfully after fixing collection and remains in progress.
