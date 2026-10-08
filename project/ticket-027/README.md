# Ticket 027 Evidence selection contracts

- **ID**: ticket-027
- **Owner**: agent:codex-stage1
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION

SESSION_EXECUTION_AUTHORIZATION: User says “wykonuj kolejne zadania, sclaaj, testuj”. Implement planfile://wellman-stage1/PLF-002, test and publish through protected review and merge. Subsequent queue slices retain their separate bounded tickets and ownership.

- [x] AC-01: Contracts distinguish report availability, feature truth, applicability and action; unknown schemas and authority-granting payloads fail closed. Hashes bind source inventory (including untracked files and removals), adoption, catalogs and revisions.
- [ ] AC-02: Full tests and managed governance pass; independent exact-head review and protected merge complete before advancing this delivery slice.

Scope: three bundled schemas, an effect-free validation/digest API and meaningful negative regressions. Documentation integrates in the later CLI slice; ticket-026 owns adoption.py, test_adoption.py and standard-selection.md and remains untouched.

Validation: all 247 tests passed, including 37 new contract regressions; managed governance passed. All three schemas pass independent Draft 2020-12 schema validation. Protected exact-head review and merge remain pending.
