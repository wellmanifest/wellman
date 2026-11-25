# Ticket 115: Add optional analysis extra for code2llm (PLF-003)

- **ID**: ticket-115
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-21

## Goal and scope

Resolve backlog ticket `PLF-003`: declare the optional `analysis` extra (`code2llm>=0.5.180; python_version >= '3.10'`) in `pyproject.toml`, update the `code2llm module analysis failed` error message in `src/wellman/adoption.py` to reference `wellman[analysis]` and `uv tool install wellman --with code2llm`, and verify both with unit tests in `tests/test_adoption.py`.

## Acceptance criteria

- [ ] AC-01: `[project.optional-dependencies]` in `pyproject.toml` declares `analysis` with `code2llm>=0.5.180`, and `recommend(..., analyze=True)` error messaging guides users to `wellman[analysis]` / `--with code2llm`.
- [ ] AC-02: `./project/governance-check.sh --base origin/main`, `.venv/bin/pytest -q`, and `wellman check --root . --json` pass cleanly.

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
| Estimated effort | 54 min |
| Planning budget | 30 min |
| Split recommended | yes |

Diagnostics: RADAR-ACCEPTANCE-MISSING, RADAR-BUDGET-EXCEEDED.
<!-- ticket-radar:end -->
