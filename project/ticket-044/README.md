# ticket-044 Validate standard effect metadata against managed control paths

- **ID**: ticket-044
- **Owner**: agent:codex-root
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION

SESSION_EXECUTION_AUTHORIZATION: User says “kontynuuj”. Continue PLF-123 via PLF-17152, test the reproduced effect-metadata gap and request independent protected publication.

Missing declarations and effects visible in managed CI/hook/review-authority paths must defer proposed changes. Path checks are a lower bound; they never prove absence of runtime effects. Existing adoption remains preserved and correctly declared effects retain explicit approval requirements. No standard adoption or control-file edits.

- [x] AC-01: Missing/incomplete effect metadata defers changes, including managed control-directory/glob scopes; ordinary files, declared-effects approvals and unchanged adoption remain correct.
- [ ] AC-02: Focused/full tests, governance and independent exact-head review and merge pass.

Validation: baseline21 regression failures/8 preservation passes; corrected158 focused integration tests before3 added positive cases, final609 full testsPASS and managed governancePASS. Existing CLI/E2E fixtures now declare their file effects; every assertion retained. Independent protected exact-head merge remains pending.
