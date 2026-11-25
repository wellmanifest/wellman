# Ticket 116: Block fleet adopt writes on governed primary main checkouts (PLF-006)

- **ID**: ticket-116
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-21

## Goal and scope

Resolve backlog ticket `PLF-006`: enforce the `wellmanifest/new-project` host contract in `src/wellman/fleet.py` so `build_plan` and `apply_plan` block pending adoption writes on governed primary or `main`/`master` checkouts that carry `project/new-ticket.sh`, while allowing already up-to-date repositories and linked ticket worktrees (`ticket/*` branches).

## Acceptance criteria

- [ ] AC-01: Governed primary/`main`/`master` checkouts with pending actions are blocked in `build_plan` and skipped in `apply_plan` with a `./project/new-ticket.sh` remediation diagnostic.
- [ ] AC-02: Up-to-date governed primary checkouts (`actions == []`) and linked ticket worktrees remain permitted.
- [ ] AC-03: Targeted `tests/test_fleet.py`, full `.venv/bin/pytest -q`, `./project/governance-check.sh --base origin/main`, and `wellman check --root . --json` pass cleanly.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.

<!-- ticket-radar:start -->
## Ticket Radar

Initial planned-scope estimate; advisory only, not execution or merge approval.

| Measure | Initial assessment |
| --- | --- |
| Impact score | 52/100 |
| Complexity | M |
| Estimated effort | 51 min |
| Planning budget | 30 min |
| Split recommended | yes |

Diagnostics: RADAR-ACCEPTANCE-MISSING, RADAR-BUDGET-EXCEEDED.
<!-- ticket-radar:end -->
