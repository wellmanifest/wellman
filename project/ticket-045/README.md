# Ticket 045: Expose evidence-bound SSOT diagnostics through Wellman CLI

- **ID**: ticket-045
- **Owner**: agent:codex-ssot-cli
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-10-08

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: the user requests continuation, implementation,
testing and governed publication of evidence-based Wellman standards and SSOT.
Continue the merged ticket-034 API with the explicit read-only CLI and documentation.
Snapshot diagnostics are advisory and do not certify current source freshness.

## Acceptance criteria

- [x] AC-01: Bounded inputs produce deterministic SSOT diagnostics; invalid or stale bindings fail without writes.
- [ ] AC-02: Full tests and governance pass; independent protected controller reviews and merges the exact head.
- [ ] AC-03: CLI smoke passes in an isolated installation built from the merged commit.
