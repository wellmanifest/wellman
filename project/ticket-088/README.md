# Ticket 088: Multipack CLI and installable distribution

- **ID**: ticket-088
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-10-31

## Goal and scope

Expose `wellman multipack validate MANIFEST` as an offline JSON interface to
the existing candidate validator. Include a documented illustrative family
with independently versioned Python/npm artifacts and an internal Rust core.
Carry version 0.21.0, lock and changelog with this material CLI implementation.

## Acceptance criteria

- [x] AC-01: Valid/invalid/missing descriptors work outside a Git checkout with deterministic JSON and authority none.
- [x] AC-02: The installed wheel's actual console entrypoint validates the example outside the source tree and reports 0.21.0.
- [ ] AC-03: Full tests, scope gate and independent protected merge pass; registry publication follows the declared Goal path.

## Session authorization

SESSION_EXECUTION_AUTHORIZATION: user requested Wellman implementation first,
reusable Python/npm capability families, optional Rust, Goal -a updates and
continued protected merging. The candidate command grants no runtime or
publication authority. Do not change the canonical URIprocess standard here.

## Validation

CLI and multipack suites: 192 passed, 8 skipped. A wheel built from a source
copy installs without dependencies into an isolated venv; its actual console
entrypoint reports 0.21.0 and validates the example outside source/Git. Missing
input returns structured JSON with exit 1. Prepared scope gate: PASS. Goal -a
performs full-suite and protected delivery checks before merge.
