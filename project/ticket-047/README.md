# Ticket 047: Reject failed and quality-invalid evidence

- **ID**: ticket-047
- **Owner**: agent:codex-evidence-proof
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-10-08

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: the user requests continuation and correction,
testing and protected merge of defects in wellmanifest standards. Reproduction:
SSOT emits SSOT_MULTIPLE_OWNERS despite an error affecting contracts-stage;
applicability trusts partial positive evidence even when exit_code is nonzero.
The existing schema already rejects inconsistent complete exit/truncation flags.
Centralize affected evidence validation without executing or adopting proposals.

## Acceptance criteria

- [x] AC-01: Failed and quality-invalid producing stages cannot prove SSOT or standard applicability; valid unrelated evidence remains usable.
- [ ] AC-02: Full tests and governance pass; protected independent exact-head review and merge.
- [ ] AC-03: An isolated installation built from the merged commit passes both regressions.
