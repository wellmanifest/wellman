# Ticket 059: Prevent and reconcile additive Wellman registration lock drift

- **ID**: ticket-059
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-14

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: continue optimization, repairs, tests and protected merges for Maskservice SSOT/nohardcode adoption. Fix the owning Wellman registrar in src/wellman/adoption.py and src/wellman/cli.py with regression tests. Additive registration must maintain an existing legacy registrar-owned digest; native package locks remain owned by their pinned adopter. Existing drift requires an explicit immutable historical registration and expected current lock digest, and must reject removal or weakening of requirements. No manual target lock edits, native adoption bypass, credential changes or direct merge.

## Acceptance criteria

- [x] AC-01: Additive registration keeps a compatible legacy lock consistent and preserves all other pins.
- [x] AC-02: Explicit historical reconciliation accepts only additive requirements and validates the expected lock digest.
- [x] AC-03: Native locks, unrelated drift, symlink targets and concurrent changes fail without writes.
- [ ] AC-04: Required source tests, CLI regressions and governance checks pass; publication uses the independent Validator.
