# Ticket 112: authority-lifecycle: skip foreign worktree-lease records

- **ID**: ticket-112
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-20

## Goal and scope

`wellman check` reported `GOV-AUTHORITY-LIFECYCLE-INVALID` for every
git-ignored local lease written by other tools in `.subactor/leases`
(e.g. `subactor.worktree-lease/v1`, `maskauth.native-ticket-worktree-lease/v1`
in maskservice/maskauth). Those files are worktree records, not
authority-lifecycle documents, so the errors were noise that blocked adopters.

Records in `.subactor/leases` whose schema is a non-`wellmanifest.`
`*worktree-lease/vN` and that carry a `worktree` field are now skipped like the
existing worktree lease records. Unknown `wellmanifest.*` schemas, foreign
leases without `worktree`, and other foreign schemas stay invalid.

## Acceptance criteria

- [x] AC-01: Foreign worktree-lease records are skipped.
- [x] AC-02: Unrecognized wellmanifest and non-worktree schemas remain invalid.
- [x] AC-03: maskauth loses the three false errors; `pytest -q tests` passes (941).

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
