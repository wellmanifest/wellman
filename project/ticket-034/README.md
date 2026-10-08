# ticket-034 Evidence-bound domain SSOT analysis

- **ID**: ticket-034
- **Owner**: agent:codex-ssot
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION

SESSION_EXECUTION_AUTHORIZATION: User requests continuation, implementation, tests and deployment of evidence-based standards and domain/logic/SSOT coherence. Implement the disjoint SSOT analyzer API and tests, validate and publish through the independent protected controller. Preserve ticket-033 selection-plan and fleet ownership.

## Accepted scope

Add a pure bounded API consuming a validated observation and explicit contract ownership declarations. Group only by declared domain, kind and contract key; lexical similarity never authorizes consolidation. Diagnose multiple owners, missing owners/references and stale or divergent generated projections. Bind results to input digests and evidence. Emit reviewable refactoring proposals without executing changes, fetching data, or granting authority. CLI integration and scanners remain follow-up work owned by their integration tickets.

## Acceptance criteria

- [x] AC-01: Domain ownership/projection findings are deterministic and preserve independent domains and contract kinds.
- [x] AC-02: Missing, stale, incomplete, contradictory or unbound evidence defers; malformed inputs fail before any effects.
- [ ] AC-03: Full tests and governance pass; independent exact-head review and protected merge deliver the API.

Validation: 23 focused tests and 415 full tests passed; managed governance passed. Independent publication pending.
