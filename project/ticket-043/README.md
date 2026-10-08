# ticket-043 Resolve repository standard relationships across every component

- **ID**: ticket-043
- **Owner**: agent:codex-root
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION

SESSION_EXECUTION_AUTHORIZATION: User says “kontynuuj, testuj, scalaj”. Continue PLF-123 via PLF-17150, fix the reproduced repository-wide relationship gap, run tests and request independent protected publication.

A repository decision currently checks only its lexicographic anchor component, missing a conflict or dependency in another component. Select all targets within the repository for repository-scoped consumers, while preserving component and repository isolation. No standard adoption or execution authority.

- [x] AC-01: Cross-component conflicts and dependencies are resolved regardless of ordering, with sibling and repository isolation.
- [ ] AC-02: Full tests, governance and independent exact-head approval and merge.

Validation: baseline regressions reproduced two failures and three isolation passes; corrected resolver 37 focused and 577 full tests pass. Managed governance passes with zero errors/warnings. No standard adoption or execution authority. Independent exact-head publication remains pending.
