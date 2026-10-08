# ticket-046 Bind analyzer snapshots to observed tool implementation bytes

- **ID**: ticket-046
- **Owner**: agent:codex-root
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION

SESSION_EXECUTION_AUTHORIZATION: User says “kontynuuj”. Continue PLF-123 via PLF-17154, repair analyzer provenance, test and request independent protected publication.

Package versions alone do not detect same-version code replacement. Fingerprint actual analyzer package bytes without importing tool/product code; bound traversal and bytes, reject unsafe paths and use fresh isolated bytecode lookup without cache writes. Existing environment-before/after artifacts and digests bind the observations. Dependency versions remain metadata, not immutable dependency bytes or conformance authority.

- [x] AC-01: Real isolated probes distinguish same-version implementations without imports; bytecode isolation and code drift preserve the prior snapshot.
- [ ] AC-02: Focused/full tests, governance and independent exact-head review and merge pass.

Validation: 618 full tests PASS, governance PASS; real pinned code2llm/redup/prefact snapshot complete. Pre-change regressions: 6 failures/1 preservation pass. Independent exact-head approval and protected merge remain required.
