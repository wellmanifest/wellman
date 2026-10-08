# ticket-042 Document evidence selection workflow and portable workspace adapter

- **ID**: ticket-042
- **Owner**: agent:codex-stage1
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION

SESSION_EXECUTION_AUTHORIZATION: User says “wykonuj kolejne zadania, sclaaj, testuj”. Execute planfile://wellman-stage1/PLF-009, run required tests and invoke independent protected review and merge.

- [x] AC-01: CLI examples match implemented flags and closed contracts, limitations and AC01–12 tests are traceable; portable wrapper delegates explicit phases without automatic updates/adoption/source generation.
- [ ] AC-02: Full suite and accepted-base managed gate pass; independent protected exact-head approval and merge.

Document the implemented evidence-selection CLI/API, pinned Python-only snapshots, explicit environment updates and human backlog boundary, and publish the tested portable workspace wrapper. Independent protected review and merge.

Validation: 572 full tests pass on integrated source. Portable example passes bash -n and 14 delegation cases. CLI help matches examples; all 19 acceptance test references resolve. Real pinned code2llm/redup/prefact fixture scan, saved plan/export and unsupported rerun preserve source/current snapshot; no adoption authority.
