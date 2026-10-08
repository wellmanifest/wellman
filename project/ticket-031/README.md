# ticket-031 Deterministic evidence applicability and action resolver

- **ID**: ticket-031
- **Owner**: agent:codex-stage1
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION

SESSION_EXECUTION_AUTHORIZATION: User says “wykonuj kolejne zadania, sclaaj, testuj”. Execute planfile://wellman-stage1/PLF-006, run required tests and invoke independent protected review and merge.

- [x] AC-01: Separate applicability/action outcomes preserve adoption, defer missing evidence/pins/cycles/conflicts, and keep LLM suggestions non-authoritative.
- [ ] AC-02: Full regression tests, managed governance and independent protected merge pass.

Bind versioned candidate rules to explicit target pins and resolve applicability independently from proposed actions; test and independently merge without effects.

Validation: 363 tests passed, including 32 resolver regressions; matching adoption artifact is required for current-observation conformance. Protected review pending.
