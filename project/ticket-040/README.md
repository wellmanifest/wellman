# ticket-040 Validate end-to-end evidence selection and preserve owned backlog records

- **ID**: ticket-040
- **Owner**: agent:codex-stage1
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION

SESSION_EXECUTION_AUTHORIZATION: User says “wykonuj kolejne zadania, sclaaj, testuj”. Execute planfile://wellman-stage1/PLF-009, run required tests and invoke independent protected review and merge.

- [x] AC-01: Multi-component plans and explicit exports preserve source, pins, hooks, CI and claimed records; JSON fixtures support pre-3.11 Python.
- [ ] AC-02: Full tests and accepted-base managed gate pass; independent protected exact-head approval and merge.

Validate component-bound keep/add/defer planning and CLI/export without source effects. Preserve claimed or incomplete matching backlog records and use portable JSON fixtures. Publish through independent protected review and merge.

Validation: 561 full tests pass, including nine component/CLI acceptance cases and 13 preservation regressions. New acceptance/selection fixtures pass Ruff F,I; changed legacy fleet files have zero new F findings compared to accepted base. Accepted-base managed gate passes.
