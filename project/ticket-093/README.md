# Ticket 093: Register standards shipping conformance.py in catalog

- **ID**: ticket-093
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-11-10

## Goal and scope

Register the five `wellmanifest/*` standard packs that ship `standard/conformance.py`
(`wellmanifest/nolimits`, `wellmanifest/auth-lifecycle`, `wellmanifest/secrets`,
`wellmanifest/clonerd`, `wellmanifest/llm-account-tool`) in `STANDARDS_CATALOG`
(`src/wellman/registry.py`), `CAPABILITIES` (`src/wellman/applicability.py`), and
`src/wellman/schemas/standard-packs.json` as `reference-only` (`S0`) standards
(`wellmanifest/wellman#91`), without fabricating unverified `runner.py` pass stubs.
Record that `wellmanifest/goal` and `wellmanifest/oql` ship package-level
`conformance.py` outside `standard/` as execution/query tool packages rather than
domain standard packs.

## Acceptance criteria

- [x] AC-01: `wellmanifest/nolimits`, `wellmanifest/auth-lifecycle`, `wellmanifest/secrets`, `wellmanifest/clonerd`, and `wellmanifest/llm-account-tool` are registered in `STANDARDS_CATALOG`, `get_standard` aliases, `CAPABILITIES`, and `standard-packs.json` with `minimum_level="S0"` and `execution_model="reference-only"`.
- [x] AC-02: `wellman info <id>` resolves all five standards while `wellman check --standard <id>` fails closed with `GOV-STANDARD-NOT-IMPLEMENTED` until dedicated runtime checkers are added.
- [x] AC-03: Classification of `wellmanifest/goal` and `wellmanifest/oql` as tool packages (outside `standard/conformance.py`) is recorded in `src/wellman/registry.py` and this ticket.
- [x] AC-04: Unit tests, `./project/governance-check.sh`, and `wellman check` pass cleanly.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
