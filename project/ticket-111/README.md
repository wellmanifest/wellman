# Ticket 111: Accept new-project lease phases and legacy worktree lease records in authority-lifecycle check

- **ID**: ticket-111
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-19

## Goal and scope

On 2026-11-19, `wellman check` on heyasa/willman `main` reported 82
GOV-AUTHORITY-LIFECYCLE-INVALID errors, all from gitignored runtime records in
`.subactor/leases/`:

- 69 legacy worktree layout records with schema `wellmanifest.worktrees/lease/v1`;
- 3 schema-less records whose nested `layout.schema` is `wellmanifest.worktrees/v5`;
- 9 `wellmanifest.worktrees/v5` records (already skipped since ticket-110);
- 1 canonical change lease in phase `editing`. `editing` is a valid phase of
  the new-project state machine (`scripts/change_lease_check.py` `PHASES`), but
  the checker did not accept it.

Scope (`src/wellman/catalog_pack_checkers.py`):

- `_CHANGE_LEASE_PHASES` also accepts the new-project phases `editing`,
  `validating`, `dispatching`, `approved` and `merged`.
- Records in `.subactor/leases/` are skipped as worktree-owned when they carry
  `wellmanifest.worktrees/v5` or `wellmanifest.worktrees/lease/v1`, or have no
  schema and a nested `layout.schema` of `wellmanifest.worktrees/v5`.
- Unknown schemas and every other location are still reported.

## Acceptance criteria

- [x] AC-01: Scope is approved by the repository owner in session (2026-11-19, "kontynuuj, scalaj"; earlier request to remove pointless standards errors).
- [x] AC-02: The new-project phases pass, and legacy worktree lease records are skipped (`tests/test_catalog_pack_checkers.py`: 8 new cases, 7 of which fail on the previous checker).
- [x] AC-03: Schema-less records that are not worktree records remain GOV-AUTHORITY-LIFECYCLE-INVALID.
- [x] AC-04: `check_authority_lifecycle` on the real heyasa/willman checkout returns 0 findings (was 82).
- [x] AC-05: The full test suite passes (936 passed, 34 skipped).

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
