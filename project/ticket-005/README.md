# Ticket 005: Adopt Wellmanifest 0.20.50 multi-agent WIP capacity

- **ID**: ticket-005
- **Owner**: codex
- **Workstream**: integration (the package binding is an integration-owned dependency declaration)
- **Status**: DONE
- **Workflow state**: DONE
- **Created**: 2026-09-22

## Goal and scope

Adopt the published immutable `wellmanifest/new-project` 0.20.50 standard
through `goal governance adopt`. This carries the multi-agent WIP default of
8 per workstream and the canonical worktree admission/lease guardrails into
this Wellman repository. The adoption must remain a standard projection; no
managed manifest hashes or lease state may be edited by hand.

## Acceptance criteria

- [x] AC-01: Scope is approved by the requesting human and allocated through
      the canonical ticket/worktree lifecycle.
- [x] AC-02: The adoption plan is generated from published revision
      `42dce766825f35b2a97cf16c9bf72e80a4a0c2d3` and applies only the files
      selected by the standard's immutable managed-file projection.
- [ ] AC-03: Governance, package, and project tests pass in the canonical
      worktree and the delivery is merged to `main`.
- [ ] AC-04: A terminal merge receipt is recorded for ticket-005.

- 0.20.46 was superseded before merge: its `wellman` runtime was never
  installable (PyPI publisher misconfigured, incomplete bundled checker).
  0.20.50 installs the runtime from the immutable `wellman-v0.20.50` Git tag
  and applies the pack baseline by the declared audit/enforce mode.
  0.20.50 runs the `wellman` gate as the CI actor in adopter workflows.

## Delivery contract

- **Accepted base**: `2f8a0b73ce552c78498629469c839d1860c478d2`
- **Target**: `main`
- **Complexity**: L; the standard projection updates 18 managed/support files.
- **Validation**: `python3 -m pytest -q`, `./project/governance-check.sh`,
  and `git diff --check`.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
