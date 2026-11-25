# Ticket 119: Release wellman 0.23.3 with PLF-003/004/005/006/010 fixes

- **ID**: ticket-119
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-21

## Goal and scope

Bump `wellman` release metadata (`VERSION`, `pyproject.toml`, `src/wellman/__init__.py`, `README.md`, `CHANGELOG.md`, `tests/test_cli.py`, `uv.lock`) to `0.23.3` to package the `PLF-003`, `PLF-004`, `PLF-005`, `PLF-006`, and `PLF-010` fixes merged on `main`.

## Acceptance criteria

- [x] AC-01: Version metadata across `VERSION`, `pyproject.toml`, `src/wellman/__init__.py`, `README.md`, `CHANGELOG.md`, `uv.lock`, and `tests/test_cli.py` is consistently updated to `0.23.3` and the test suite passes.
- [x] AC-02: Repository governance check and `wellman check` pass cleanly without errors or warnings.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.

<!-- ticket-radar:start -->
## Ticket Radar

Initial planned-scope estimate; advisory only, not execution or merge approval.

| Measure | Initial assessment |
| --- | --- |
| Impact score | 72/100 |
| Complexity | L |
| Estimated effort | 74 min |
| Planning budget | 30 min |
| Split recommended | yes |

Diagnostics: RADAR-ACCEPTANCE-MISSING, RADAR-BUDGET-EXCEEDED.
<!-- ticket-radar:end -->
