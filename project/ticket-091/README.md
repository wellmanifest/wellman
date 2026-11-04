# Ticket 091: Skip virtualenv and dependency trees in the nohardcode path scan

- **ID**: ticket-091
- **Owner**: claude-code
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-04

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: during a 2026-11-04 audit of a consuming
repository the user asked the agent to "analizuj, poprawiaj, scalaj, testuj"
the findings. This bounded request authorizes the fix, scoped tests and a
request for protected publication of this one change. It does not authorize a
direct merge, an administrative bypass or a deployment.

Defect: `ConformanceRunner.check_nohardcode` walked `src`, `app`, `lib`,
`packages` and `.governance` with `rglob` and skipped only path components
named `.venv`, `.worktrees`, `__pycache__`, `.git`, `test_fixtures` and
`_bundled`. A virtualenv under a different name (for example `packages/venv`)
or any `node_modules` / `site-packages` tree was scanned as project source.
Measured on a consuming repository: 60 findings (24 errors) of which 54 came
from installed dependencies, in 16.4 s; the gate was permanently red for
reasons unrelated to any change.

Fix: walk with `os.walk`, pruning `venv`, `node_modules`, `site-packages` and
any directory that contains `pyvenv.cfg`, whatever its name. After the fix the
same repository yields 6 findings (1 error) in 0.1 s and none from dependency
trees. Project source is still scanned.

Out of scope: the remaining finding in a managed `ticket-lifecycle` copy
(`/tmp/work` literal), which belongs to its owning standard.

## Acceptance criteria

- [x] AC-01: New regression test fails before the change and passes after it.
- [x] AC-02: `tests/` passes in full and the change adds no lint findings versus HEAD.
- [ ] AC-03: Exact-head protected CI and independent publication succeed.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
