# ticket-035 Pinned read-only analyzer snapshots

- **ID**: ticket-035
- **Owner**: agent:codex-root
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION

SESSION_EXECUTION_AUTHORIZATION: User says “kontynuuj, zalegle zadania”, with existing authorization to test, push and invoke protected merge. Resume PLF-126 / Willmux #315 after native033/034 integration.

- [x] AC-01: Pinned independent analyzer stages, isolated exact shared scope, schema/source binding, complete atomic publication and meaningful failure regressions.
- [ ] AC-02: Full suite, governance, Ruff and independent exact-head protected publication.

Validation: 23 producer regressions passed. Actual pinned analyzers all exit0 after fixing prefact CLI invocation; code2llm graph remains correctly partial because the existing adapter assumes node entrypoint identities and node file fields. Preserve that follow-up outside this bounded producer scope; incomplete batches do not replace current.

Full validation:467 tests passed; managed governance and Ruff pass. Publication remains pending independent exact-head trusted approval. Operational adapter follow-up: PLF-127, serialized after this bounded producer slice. Analyzer runtime installation is separate, with source archive SHA receipts and complete environment lock in private recovery.
