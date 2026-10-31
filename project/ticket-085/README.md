# Ticket 085: Synchronize bundled standard catalog

- **ID**: ticket-085
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-10-31

## Goal and scope

Include the already registered data-plane pack in Wellman bundled composition metadata. Do not change execution authority, canonical standard behavior or adopted governance pins.

## Acceptance criteria

- [x] AC-01: Bundled catalog pack identities match the runtime registry and dependency checks pass.

## Session authorization

SESSION_EXECUTION_AUTHORIZATION: user requested continuation, test fixes and protected merging. Independent exact-head approval remains required.

## Validation

27 registry-dependency and multipack tests passed, including the exact assertion that failed in the preceding full suite. Managed governance passed.
