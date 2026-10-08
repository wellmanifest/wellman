# ticket-030 Read-only adoption pins drift and conformance inspection

- **ID**: ticket-030
- **Owner**: agent:codex-stage1
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION

SESSION_EXECUTION_AUTHORIZATION: User says “wykonuj kolejne zadania, sclaaj, testuj”. Execute planfile://wellman-stage1/PLF-005, run required tests and invoke independent protected review and merge.

- [x] AC-01: Missing and malformed locks, declaration-only profiles, drift, exception claims and trusted exact-state validation produce distinct read-only outcomes.
- [ ] AC-02: Full regression tests, managed governance and independent protected merge pass.

Inspect existing adoption, requirements, pins, managed digests and exception claims without executing validators or changing files; test and independently merge.

Validation: 331 tests passed, including 27 adoption inspection regressions; managed governance PASS. Protected merge pending.
