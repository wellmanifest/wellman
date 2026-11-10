# Ticket 096: Implement S1 static conformance checkers for nohardcode, semver, and ssot

- **ID**: ticket-096
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-11-10

## Goal and scope

Implement deterministic, dependency-free, fail-closed static conformance
checkers for `wellmanifest/nohardcode`, `wellmanifest/semver`, and
`wellmanifest/ssot` in `wellman`, and promote `wellmanifest/semver` and
`wellmanifest/ssot` from `S0` (`reference-only`) to `S1` (`local-conformance`)
while preserving non-effectful boundaries (`excludes` retaining `execution
authority` and `verified runtime conformance`).

## Acceptance criteria

- [x] AC-01: `src/wellman/domain_pack_checkers.py` validates `nohardcode` policy/waiver/engine contracts, `semver` version carriers and embedded-release/pipeline-run/hardware-matrix/policy manifests, and `ssot` decision/interview/standards-lock contracts with duplicate-key rejection.
- [x] AC-02: `src/wellman/registry.py` promotes `wellmanifest/semver` and `wellmanifest/ssot` to `S1` / `local-conformance` without adding them to mandatory `baseline` requirements or breaking historical registration fixtures.
- [x] AC-03: Real-world upstream repositories (`wellmanifest/nohardcode`, `wellmanifest/semver`, `wellmanifest/ssot`), full test suite including `tests/test_domain_pack_checkers.py` and `tests/test_registry.py`, `./project/governance-check.sh`, and `wellman check` pass.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
