# Ticket 095: Implement static conformance checkers for conformance-pack standards

- **ID**: ticket-095
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-11-10

## Goal and scope

Implement deterministic, dependency-free static conformance checkers (`S1` /
`local-conformance`) in `src/wellman/conformance_pack_checkers.py` and wire them
into `ConformanceRunner` (`src/wellman/runner.py`) and `STANDARDS_CATALOG`
(`src/wellman/registry.py`) for the five `wellmanifest/*` packs registered in
`ticket-093`:
- `wellmanifest/nolimits`
- `wellmanifest/auth-lifecycle`
- `wellmanifest/secrets`
- `wellmanifest/clonerd`
- `wellmanifest/llm-account-tool`

## Acceptance criteria

- [x] AC-01: `wellman check --standard <id>` executes deterministic static conformance checks with stable finding codes for `wellmanifest/nolimits`, `wellmanifest/auth-lifecycle`, `wellmanifest/secrets`, `wellmanifest/clonerd`, and `wellmanifest/llm-account-tool` (failing closed when required artifacts are missing or invalid).
- [x] AC-02: `STANDARDS_CATALOG` promotes those five standards to `minimum_level="S1"` and `execution_model="local-conformance"`, while retaining `excludes=["execution authority", "verified runtime conformance"]`.
- [x] AC-03: Aggregate `ConformanceRunner.run_all()` executes these checkers when registered in `.governance/standard-requirements.json` or when their `.governance/*.json` configuration files exist, without false-failing unrelated repositories.
- [x] AC-04: Positive and negative unit tests (`tests/test_conformance_pack_checkers.py` and `tests/test_registry.py`), `./project/governance-check.sh`, and `wellman check` pass cleanly, and `src/wellman/conformance_pack_checkers.py` remains under the 500-line module limit.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
