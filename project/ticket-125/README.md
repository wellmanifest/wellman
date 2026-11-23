# Ticket 125: Sync bundled ticket_activity with new-project owner-decision resolver

- **ID**: ticket-125
- **Owner**: tom
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-23

## Goal and scope

Sync `src/wellman/_bundled/ticket_activity.py` byte for byte with
`wellmanifest/new-project` main (0043e90, ticket-471 / PR #664). The bundled overlap
and governance checkers resolve every checkout with this copy; the previous copy
(last synced by ticket-101) rejected a policy naming `owner-decision`, which made
`wellman check` fail on every checkout of the clone (observed on 2026-11-23).
Phase two of wellmanifest/new-project#661: new-project can enable `cancelled` in
its default policy once this runtime is released. Requested by the owner.

## Acceptance criteria

- [x] AC-01: The bundled resolver equals new-project main; `tests/test_bundled_ticket_activity.py` passes, and the remaining runner/governance/fleet failures are identical on main.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.

<!-- ticket-radar:start -->
## Ticket Radar

Initial planned-scope estimate; advisory only, not execution or merge approval.

| Measure | Initial assessment |
| --- | --- |
| Impact score | 44/100 |
| Complexity | M |
| Estimated effort | 34 min |
| Planning budget | 30 min |
| Split recommended | yes |

Diagnostics: RADAR-ACCEPTANCE-MISSING, RADAR-BUDGET-EXCEEDED.
<!-- ticket-radar:end -->
