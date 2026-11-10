# Ticket 098: Promote nohardcode and URI/task packs to S1 and preserve historical lock levels

- **ID**: ticket-098
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-11-10

## Goal and scope

1. Preserve recorded `minimumLevel` entries on pre-existing unrequested `requirements` items when `reconcile_lock_from` is active in `src/wellman/adoption.py` while still expanding missing `requires` dependencies.
2. Promote `wellmanifest/nohardcode`, `wellmanifest/uriprocess`, `wellmanifest/taskand`, and `wellmanifest/nl-uri-dsl-llm` from `S0` (`reference-only`) to `S1` (`local-conformance`), keeping non-effectful `excludes` (`execution authority`, `verified runtime conformance`).
3. Implement deterministic, dependency-free S1 checkers in `src/wellman/uri_pack_checkers.py` for `uriprocess`, `taskand`, and `nl-uri-dsl-llm`.

## Acceptance criteria

- [x] AC-01: `PYTHONPATH=src pytest -n auto -q` passes across the full suite, including historical lock reconciliation and positive/negative S1 conformance tests for `nohardcode`, `uriprocess`, `taskand`, and `nl-uri-dsl-llm`.
- [x] AC-02: Real-world upstream pack checks (`nohardcode`, `uriprocess`, `taskand`, `nl-uri-dsl-llm`), `./project/governance-check.sh`, and `wellman check --root .` pass with zero errors.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
