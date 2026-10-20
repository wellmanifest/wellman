# Ticket 067: Bind Python execution to the owning checkout

- **ID**: ticket-067
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-20

## Authorization and outcome

SESSION_EXECUTION_AUTHORIZATION: the user requests autonomous correction of project path selection, Wellmanifest standardization and Wellman enforcement after a Willman test command inherited host-wide TMPDIR. Implement an explicit Python/pytest launch boundary in the canonical Wellman CLI, with current Git checkout identity, a checkout-owned ignored private temporary directory, and a validated local virtual environment. An explicitly requested primary-checkout environment may be reused only after Git establishes that it belongs to this same registered repository. Never fall back to a global Python.

Static governance checks do not intercept arbitrary shell execution. This launcher checks its own admission and environment; it is not a filesystem sandbox, execution lease, test result, trusted approval or automatic deployment. Preserve protected CI runtimes, historical evidence, active worktrees and the independently owned new-project ticket-354. The installed legacy wellman entry point comes from new-project; distribution convergence is a separate owner dependency, not a reason to overwrite it.

## Acceptance criteria

- [x] AC-01: Resolve the actual registered checkout from nested paths without inherited Git selectors; reject symlinked/non-Git targets and unrelated interpreters before running the requested command.
- [x] AC-02: Prefer this checkout's real .venv. Primary environment reuse requires an explicit flag and verified Git relationship. Fail when the environment is absent or unusable.
- [x] AC-03: Create private ignored checkout-local scratch, override inherited temporary-directory settings, remove ambient Python import overrides and user site, and retain a bounded local context/result receipt without raw arguments or secrets.
- [x] AC-04: Actual child-process regression tests cover local and primary environments, cross-project and symlink refusal, nested roots, concurrent runs and nonzero child status. Run affected CLI tests and the adopted governance gate.
- [ ] AC-05: Retain exact source and qualification evidence; request protected independent publication and record remaining integration separately.

## Qualification

The first local-scratch run exposed an existing Git discovery leak from non-Git test fixtures to their parent checkout. The next run failed closed but exposed a second inconsistent ancestor scan in bootstrap. Both paths now honor the same discovery ceiling while preserving the broken-metadata refusal within the boundary. The actual affected suites pass: 206 passed, 8 existing skips. No additional skip or deselection was introduced. A concurrent cache creation race found by the real parallel-process case was corrected with idempotent ancestor creation and path revalidation.

Executable tests run through this checkout's .venv and wellman run. Receipts and scratch are inside its ignored .subactor directories. First-failure logs and exact generated fixture files remain preserved there; no unrelated source was removed. The adopted governance gate passed after correction.

The real Willman ticket-289 qualification through the launcher passed 18 tests and 8 subtests, with scratch beneath that same worktree. Primary-venv reuse was explicit and verified through registered Git identity. Source implementation is a candidate; global CLI convergence and mandatory adapter adoption are tracked in wellmanifest/new-project#501.
