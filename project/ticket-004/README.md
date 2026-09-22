# Ticket 004: Native canonical worktree admission and scalable multi-agent WIP

- **ID**: ticket-004
- **Owner**: human-approved
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-09-22

## Goal and scope

To be completed from human-owned input.

## Acceptance criteria

- [x] AC-01: Scope is approved by the human owner in the active session.
- [x] AC-02: `wellman check` and `wellman gate` reject Git checkouts below `/tmp`
  and linked worktrees that do not use the canonical v5 path/branch identity.
- [ ] AC-03: The upstream managed governance base raises the concurrent-ticket
  capacity for multi-agent repositories; this adopter must then consume that
  immutable release instead of overriding the managed projection locally.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
