# Ticket 022: Preserve native governance during explicit scaffold adoption

- **ID**: ticket-022
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-10-03

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: the user requested continued testing, repair,
push and protected merge of outstanding project work. A disposable reproduction
showed explicit scaffold adoption replacing a native governance manifest.
Repair only the Wellman CLI guard, its regression tests and usage documentation.
Publish through the independent exact-head Validator after native checks pass.

## Acceptance criteria

- [x] AC-01: Explicit scaffold adoption preserves native governance and immutable adoption records before any write; legacy scaffold replacement and additive registration still work.
- [x] AC-02: Regression tests and the native gate pass on the delivered head.
- [ ] AC-03: Exact-head independent approval and protected merge have an external terminal receipt.
