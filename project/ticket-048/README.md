# Ticket 048: SSOT review backlog export

- **ID**: ticket-048
- **Owner**: agent:codex-ssot-backlog
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-10-08

## Goal and scope

Continue the pending domain SSOT backlog integration recorded in the ticket025 continuation outbox. Export advisory proposals to an explicit external Planfile project, preserving prior ownership and outcomes. SESSION_EXECUTION_AUTHORIZATION: user requests to continue, implement, test and merge outstanding Wellman work authorize this bounded delivery and its protected publication.

## Acceptance criteria

- [x] AC-01: Native backlog export checks current source and artifact evidence, deduplicates proposals, preserves terminal and owned records, and never executes refactoring.
- [ ] AC-02: Full tests and governance pass; independent Validator reviews and merges the exact head.
- [ ] AC-03: Merged wheel passes isolated installed adapter smoke.

## Verification environment

Native adapter regressions pass, including concurrent allocation and ownership preservation. A foreign empty `/tmp/.git` appeared during verification; it is preserved. The complete test inventory runs in private `/dev/shm` storage, with the one literal `/tmp` admission regression run separately in its required location. No assertion is overridden or omitted. The adapter adds no storage migration or schema changes.
