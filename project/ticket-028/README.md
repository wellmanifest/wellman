# ticket-028 Manifest component boundaries and static source inventory

- **ID**: ticket-028
- **Owner**: agent:codex-stage1
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION

SESSION_EXECUTION_AUTHORIZATION: User says “wykonuj kolejne zadania, sclaaj, testuj”. Execute planfile://wellman-stage1/PLF-003, run required tests and invoke independent protected review and merge.

- [x] AC-01: Manifest boundaries, file classes and all staged/unstaged/untracked/deleted source changes are bound with explicit coverage gaps and symlink/budget limits.
- [ ] AC-02: Full regression tests, managed governance and independent exact-head protected merge pass.

Read-only inventory binds Git, manifests, relevant local changes and per-file classifications; test and protected merge the bounded component API.

Validation: 275 tests passed, including 26 component inventory regressions; managed governance PASS. Protected review and merge pending.
