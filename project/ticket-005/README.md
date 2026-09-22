# Ticket 005: Adopt Wellmanifest 0.20.46 multi-agent WIP capacity

- **ID**: ticket-005
- **Owner**: codex
- **Workstream**: integration (the package binding is an integration-owned dependency declaration)
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-09-22

## Goal and scope

Adopt the published immutable `wellmanifest/new-project` 0.20.46 standard
through `goal governance adopt`. This carries the multi-agent WIP default of
8 per workstream and the canonical worktree admission/lease guardrails into
this Wellman repository. The adoption must remain a standard projection; no
managed manifest hashes or lease state may be edited by hand.

## Acceptance criteria

- [x] AC-01: Scope is approved by the requesting human and allocated through
      the canonical ticket/worktree lifecycle.
- [x] AC-02: The adoption plan is generated from published revision
      `44fb615715f64ca3be6502669d508dfe8e3078da` and applies only the files
      selected by the standard's immutable managed-file projection.
- [ ] AC-03: Governance, package, and project tests pass in the canonical
      worktree and the delivery is merged to `main`.
- [ ] AC-04: A terminal merge receipt is recorded for ticket-005.

## Delivery contract

- **Accepted base**: `2f8a0b73ce552c78498629469c839d1860c478d2`
- **Target**: `main`
- **Complexity**: L; the standard projection updates 18 managed/support files.
- **Validation**: `python3 -m pytest -q`, `./project/governance-check.sh`,
  and `git diff --check`.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
