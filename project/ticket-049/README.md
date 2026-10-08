# Ticket 049: Explicit SSOT CLI backlog export

- **ID**: ticket-049
- **Owner**: agent:codex-ssot-cli-export
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-10-08

## Goal and scope

Resume `ssot-cli-export` from the ticket048 continuation outbox. Expose the merged SSOT native backlog adapter through an explicit CLI mode and document the data-only verification context. SESSION_EXECUTION_AUTHORIZATION: the user's continuation, implementation, testing and merging requests authorize this bounded delivery and protected publication.

## Acceptance criteria

- [x] AC-01: CLI export is explicit, bounded and evidence-checked; receipts preserve dedupe, terminal and external ownership semantics; snapshot analysis remains free of effects.
- [ ] AC-02: Full tests and governance pass; the independent Validator approves and the protected controller merges the exact head.
- [ ] AC-03: Installed merged wheel passes CLI backlog smoke.

## Verification environment

Run all tests in private `/dev/shm` fixtures and run the literal `/tmp` admission regression separately. This preserves the foreign empty `/tmp/.git`; no assertion is overridden or omitted. Existing lint findings are unchanged from the accepted base.
