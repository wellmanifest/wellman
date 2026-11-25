# Ticket 117: Derive reuse recommendation from redup evidence and fix receipt remediation (PLF-004, PLF-005)

- **ID**: ticket-117
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-21

## Goal and scope

Resolve backlog tickets `PLF-004` and `PLF-005`:
- Derive `wellmanifest/reuse` recommendations in `src/wellman/adoption.py` from supplied `--evidence redup=...` reports when clone groups meet `REUSE-002` thresholds (`>= 10` lines, `>= 0.80` similarity or `exact` match).
- Fix `GOV-REUSE-NO-RECEIPT` remediation text in `src/wellman/runner.py` to point to the `wellmanifest/reuse` (`wellmanifest-reuse`) script with `--project .` instead of a target-absent `scripts/record_scan_receipt.py`.

## Acceptance criteria

- [ ] AC-01: `recommend(..., evidence=[('redup', ...)])` adds `wellmanifest/reuse` when qualifying clone groups exist (`>=10` lines, `>=0.80` similarity) and skips when below thresholds.
- [ ] AC-02: `GOV-REUSE-NO-RECEIPT` remediation references `wellmanifest/reuse` / `wellmanifest-reuse` and `--project .`.
- [ ] AC-03: `tests/test_adoption.py`, `tests/test_runner.py`, `./project/governance-check.sh --base origin/main`, `wellman check --root . --json`, and full `.venv/bin/pytest -q` pass cleanly.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.

<!-- ticket-radar:start -->
## Ticket Radar

Initial planned-scope estimate; advisory only, not execution or merge approval.

| Measure | Initial assessment |
| --- | --- |
| Impact score | 56/100 |
| Complexity | M |
| Estimated effort | 57 min |
| Planning budget | 30 min |
| Split recommended | yes |

Diagnostics: RADAR-ACCEPTANCE-MISSING, RADAR-BUDGET-EXCEEDED.
<!-- ticket-radar:end -->
