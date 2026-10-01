# Ticket 021: Canonical Worktrees v5 admission

- **ID**: ticket-021
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-10-02

## Goal and scope

Fix Wellman rejecting registered canonical Worktrees v5 branches (`ticket/NNN-slug`) and publish the correction as 0.20.38. Preserve system-temp, path, registration and identity guards.

## Acceptance criteria

- [x] AC-01: Git-backed positive and adversarial worktree admission tests pass.
- [x] AC-02: Full tests, source version consistency and managed governance pass.
- [ ] AC-03: Exact-head independent Validator approval and protected merge complete.

## Validation

Full source suite: 157 passed. Git-backed admission cases preserve canonical ticket/slug matching and reject legacy, detached and noncanonical worktrees. The corrected source accepts the real canonical IMGL ticket-008 checkout; metadata and version consistency pass. Required protected publication remains pending.
