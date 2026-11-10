# Ticket 101: Sync bundled activity and overlap checkers and raise worktree check timeout

- **ID**: ticket-101
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-10

## Goal and scope

Synchronize `src/wellman/_bundled/ticket_activity.py` and `src/wellman/_bundled/worktree_overlap_check.py` with upstream `wellmanifest/new-project`, eliminate redundant `git status` and disjoint-pair `git merge-tree` subprocesses in `worktree_overlap_check.py`, and raise `ConformanceRunner.check_worktrees()` subprocess timeout from `60` to `180` seconds for multi-worktree repositories under heavy host I/O load.

- Sync `src/wellman/_bundled/ticket_activity.py` to include `ActivityReadBatch` ancestry/branch-head batching and checkout-scoped `worktree_registration` fencing (so concurrent commits in unrelated sibling worktrees no longer trigger false `GOV-TICKET-ACTIVITY-001` errors).
- Sync `src/wellman/_bundled/worktree_overlap_check.py` with NUL-framed Git `-z` decoding, single-pass `unignored_dirty_paths` status inspection, and disjoint-pair `merge_tree_conflicts` skipping when `shared_default` holds and `first_changes & second_changes` is empty.
- Raise `check_worktrees()` subprocess timeout in `src/wellman/runner.py` from `60s` to `180s`.

## Acceptance criteria

- [x] AC-01: Bundled `ticket_activity.py` and `worktree_overlap_check.py` isolate sibling-worktree registrations, inspect dirty state in one `git status -z` pass per checkout, skip `merge_tree_conflicts` on disjoint shared-default checkout pairs, and `ConformanceRunner.check_worktrees()` uses a `180s` timeout.
- [x] AC-02: `pytest`, `./project/governance-check.sh`, and `wellman check` pass cleanly with zero errors.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
