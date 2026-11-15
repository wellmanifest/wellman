# Ticket 106: Bound complete worktree conformance scans

- **ID**: ticket-106
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-11-15

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: the user requested verification and repair of
the Heyasa–Tellmesh audit and renewed "kontynuuj,scalaj" authorization.
The actual unchanged adopted worktree checker completed six checkout
observations with zero findings in 394.956 seconds. The aggregate Wellman
CLI instead stopped its child after 180 seconds.

Increase only that finite worktree-child budget to 480 seconds. Preserve
the command, interpreter, input pins, workspace and identity scope, complete
report validation, all findings and failure propagation. Scope is two
material files, one component, no interface or runtime dependency changes.

Bounded implementation: maxActiveMinutes=90 from allocation at
2026-11-15T22:18:02Z; accepted base
1080036f14f6be5e97e602757481fe432ca733bb. The native allocator owns the
session identity recorded in the lease; the safe continuity stream name is
audit-wellman-worktree-budget-20261115t2214z.

## Acceptance criteria

- [x] AC-01: A regression covering the observed 395-second scan fails at the old budget.
- [x] AC-02: The bounded 480-second child completes that observation; missing,
  timed-out, nonzero and incomplete checker results still fail closed.
- [x] AC-03: Targeted regressions and managed governance pass with exact input hashes.
- [ ] AC-04: Exact-head/current-base checks and independent Validator lead to source merge.

## Operational evidence

External evidence: artifact:audit-wellman-worktree-budget-20261115t2204z
Published source, installed tooling and actual runtime observations are separate.
The existing immutable tool release is preserved while this source is verified.

Local verification: runner/CLI suite 180 passed and 8 skipped (optional capabilities),
80.37 seconds. The old-budget regression failed as expected before the source
change. Managed governance passed with zero errors and warnings.
