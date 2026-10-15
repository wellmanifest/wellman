# Ticket 060: Fail closed on worktree checker failures and invalid check roots

- **ID**: ticket-060
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-10-15

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: the user said "wykonaj" for the reviewed repair plan tracked by maskservice PLF-15923. This slice repairs Wellman worktree conformance and check/gate root admission. Preserve existing adoption, registered checkout identity, read-only checks and independent publication boundaries.

Reject missing or failing overlap checkers, including nonzero exits without recognizable text, unreadable checkouts and unverified observations. Resolve nested check roots to the actual Git checkout before validating registered worktree identity; malformed and non-Git targets cannot pass worktree conformance. Reject inherited Git location overrides and symlinked requested paths. Do not claim runtime sandbox enforcement from a static conformance result.

This ticket does not change standard pins, source governance copies, global agent configuration, credentials, protected policy or any other repository. Later contract and executor slices remain separate under PLF-15923.

## Acceptance criteria

- [x] AC-01: Checker absence, execution exceptions and every nonzero exit fail with deterministic error findings, preserving diagnostics.
- [x] AC-02: check/gate bind nested requests to their actual registered Git checkout; invalid targets fail, including temporary/legacy linked checkouts and inherited Git selectors.
- [x] AC-03: Regression tests, full package tests and the managed governance gate pass. Required test temporary files remain in this checkout's ignored cache.
- [ ] AC-04: Record exact source, checks, commit, publication and remaining enforcement work separately; protected review is required before merge.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.

## Validation and delivery

The final full suite passed with 798 tests (250.38 seconds); the receipt is `.subactor/receipts/ticket-060/full-final.xml`. The managed governance gate passed with zero errors and warnings. Test execution uses a private mount namespace: host paths are read-only, and process `/tmp` is backed by this worktree’s ignored cache. No test or helper source is stored in the host temporary directory.

The live nested-root check resolves `docs` to this registered checkout and reports `runtime_enforcement=not_checked`. Conformance verifies adopted checker hashes; it grants no runtime, review or merge authority.

Protected Validator configuration for `wellmanifest/wellman` is present. Runtime verification, exact-head independent review and publication receipts remain required. This slice changes no deployed package. Remaining PLF-15923 work includes standard contracts, executor mediation, negative runtime tests and pinned rollout.

The adopted continuity helper rejects the allocator-supported compact intent with `GOV-CONTINUITY-001: intent target branch must be a bounded non-empty string`. No managed source or intent is rewritten to bypass that defect. A bounded exact-state checkpoint is retained at `.subactor/receipts/ticket-060/checkpoint.json`; the parent queue records a source repair for new-project.
