# Ticket 023: Preserve native standard pins during fleet adoption

- **ID**: ticket-023
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-10-03

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: the user requested continued testing, repair,
push and protected merge. A disposable fixture showed fleet adoption replacing
native new-project version 0.20.80 with the Wellman CLI version. Repair only the
fleet version-header boundary and its regression tests. Recheck the adoption at
apply time, including a partial lock with no manifest. Existing product roots,
publisher policy and controller deployment remain outside this scope.

## Acceptance criteria

- [x] AC-01: Native standard pins and partial locked adoption remain unchanged;
  legacy profile version updates and additive native adoption still work.
- [x] AC-02: Regression tests and the native gate pass on the delivered head.
- [ ] AC-03: Independent exact-head approval and protected merge have an external receipt.
