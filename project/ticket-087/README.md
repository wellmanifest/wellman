# Ticket 087: Reusable multipack identities and release declarations

- **ID**: ticket-087
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-10-31

## Goal and scope

Extend the existing offline candidate validator without a competing standard:
preserve exact process URI namespaces, support an explicit independent stable
version policy, and declare unpublished internal cores alongside npm/PyPI
artifacts. Keep lockstep as the compatibility default and every authority
claim at none. No runtime execution, registry upload or governance edits.

## Acceptance criteria

- [x] AC-01: Existing descriptors and lockstep mismatch rejection remain compatible.
- [x] AC-02: Foreign URI namespaces, independently versioned bindings and an internal Rust core validate without rewriting inputs.
- [ ] AC-03: Invalid URI structure, unknown policy and non-boolean publication flags fail; full tests and the scope gate pass before protected merge.

## Session authorization

SESSION_EXECUTION_AUTHORIZATION: the user requested reusable Python/npm packs,
optional Rust, compatible URI-process standards and continued protected merges.
This bounded application change prepares the existing Wellman candidate while
URIprocess native adoption and its independent bootstrap prerequisite wait.

## Validation

Multipack regression suite: 44 passed. The complete prepared-file scope gate
passed without errors or warnings. Goal -a will run the complete Python suite
before commit and protected PR delivery. Registry release/version projections
are deferred to the material CLI integration that consumes this candidate.
