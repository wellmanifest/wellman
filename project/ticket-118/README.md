# Ticket 118: Add native wellmanifest/gui and wellmanifest/brand checkers (PLF-010)

- **ID**: ticket-118
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-21

## Goal and scope

Resolve backlog ticket `PLF-010`: register `wellmanifest/gui` and `wellmanifest/brand` in the standards catalog, pack routing manifest, applicability capabilities, validator checked set, and implement deterministic conformance checkers (`check_gui_pack`, `check_brand_pack`) validating GUI view schemas, panel layout / TUI-GUI parity, brand color hex tokens, and WCAG AA contrast ratios.

## Acceptance criteria

- [ ] AC-01: `wellmanifest/gui` and `wellmanifest/brand` are registered in `STANDARDS_CATALOG`, `standard-packs.json`, `applicability.CAPABILITIES`, `validator.py`, and `ConformanceRunner`.
- [ ] AC-02: `check_gui_pack` detects missing declarations, invalid schemas, landing/public toolbar violations, and TUI/GUI parity gaps (`GOV-GUI-*`).
- [ ] AC-03: `check_brand_pack` detects missing descriptors, invalid hex tokens, missing profile binding, and WCAG AA contrast failures (`GOV-BRAND-*`).
- [ ] AC-04: Targeted tests, `./project/governance-check.sh --base origin/main`, `wellman check --root . --json`, and full `.venv/bin/pytest -q` pass cleanly.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.

<!-- ticket-radar:start -->
## Ticket Radar

Initial planned-scope estimate; advisory only, not execution or merge approval.

| Measure | Initial assessment |
| --- | --- |
| Impact score | 68/100 |
| Complexity | L |
| Estimated effort | 73 min |
| Planning budget | 30 min |
| Split recommended | yes |

Diagnostics: RADAR-ACCEPTANCE-MISSING, RADAR-BUDGET-EXCEEDED.
<!-- ticket-radar:end -->
