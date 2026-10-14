# Ticket 058: Admit verified absorbed Git submodules in wellman checks

- **ID**: ticket-058
- **Owner**: codex
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-10-14

## Goal and scope

Fix the observed `GOV-WORKTREE-ADMISSION-002` false rejection for the absorbed `maskservice-discovery` submodule in C2004. Git reports its primary record as the module administration directory even though `core.worktree`, the superproject and its tracked gitlink identify the real checkout.

SESSION_EXECUTION_AUTHORIZATION: the operator requested using Wellman and correcting standards errors found during C2004 SSOT/configuration validation. This includes the declared independent publication process. It does not authorize device writes or Git metadata repair.

Implementation scope is `src/wellman/cli.py` and `tests/test_cli.py`. Preserve temporary-checkout rejection, exact superproject registration and canonical parent worktree requirements. No release projection or runtime dependency changes.

## Acceptance criteria

- [x] AC-01: Real Git fixtures admit an absorbed primary and a module in a canonical parent worktree; reject an invalid parent, missing gitlink and unrelated separate Git directory.
- [x] AC-02: Focused CLI and full tests plus the managed governance gate pass.
- [ ] AC-03: Exact-head checks, independent Validator review and actual protected publication are observed.

## Tracking boundary

Local test logs and continuity receipts remain ignored. PASS test evidence does not approve publication.

## Verification evidence

- The original implementation failed both real-Git positive fixtures (2 failed, 3 passed).
- The corrected full suite passed: 701 passed, 34 skipped. Existing optional skips remain explicitly unexecuted.
- The initial repository-local fixture root caused unrelated bootstrap tests to resolve the enclosing checkout; two generated untracked governance projections were preserved in ignored recovery storage and their original absence restored. Delivery source and managed metadata were not replaced. The full suite uses ephemeral /tmp fixtures for its explicit system-temporary rejection and non-Git bootstrap contracts; positive Git registration fixtures and delivery remain in ignored local storage/canonical worktree.
- The candidate CLI accepts the real C2004 discovery submodule with zero errors and the existing missing-lock warning. This is candidate verification, not published adoption.
- Independent exact-head review and publication are pending.
