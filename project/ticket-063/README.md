# Ticket 063: Exclude .subactor/cache from changed_paths in governance check

- **ID**: ticket-063
- **Owner**: tom
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-19

## Goal and scope

Exclude `.subactor/cache/` runtime verification artifacts (such as Koru sandboxed `filter.bpf` files) from `changed_paths` in `src/wellman/_bundled/governance_check.py` so they do not trigger false-positive `GOV-TICKET-005` errors.

## Acceptance criteria

- [x] AC-01: `changed_paths()` filters out `.subactor/cache/` entries in both explicit and Git-derived modes, covered by unit tests in `tests/test_governance_check.py`.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.

