# Ticket 032: Canonical extendable adoption package maps

- **ID**: ticket-032
- **Owner**: agent:codex-root
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-10-08

## Goal and scope

PLF-124 / paxlet-com/willmux#311 reproduces PACKAGE_MAP_UNKNOWN on three valid
production repositories: new-project uses managed/seed/extendable, while the
inspector admitted managed/seed/merge. Native030 PR35 is integrated; active
native031 owns applicability.py and its test only. Keep that author and checkout
intact and correct only adoption_inspection.py and its regression tests here.

SESSION_EXECUTION_AUTHORIZATION: user requested investigation, fixes, tests and
protected merges; preserve active author and queue corrections after integration.
The native allocator and fresh disjoint admission observe native030 integrated
and this follow-up scope free. No transfer of the author's lease or worktree.

## Acceptance criteria

- [x] AC-01: Valid canonical extendable maps are parsed; invalid strategies,
  unauthorized source/target pairs, malformed fields and unsafe paths are unknown.
  Inspection preserves local bytes and grants no conformance without trust.
- [ ] AC-02: Regression/full tests, three-repository reproducer, governance and
  independent protected exact-head publication succeed.

## Validation

Before the correction: 8 regression failures (48 existing cases pass). After:
56 inspection tests, 3 real production package-map reproductions and 360 full
tests pass. Ruff and the managed governance gate pass. Extension instance
bytes are bound to material digests; changed or excluded instances cannot be
certified. Exact-head independent publication remains pending.
