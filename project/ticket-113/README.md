# Ticket 113: Release wellman 0.23.2 with ticket-111 and ticket-112 checker fixes

- **ID**: ticket-113
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-21

## Goal and scope

Bump coupled release metadata (`VERSION`, `pyproject.toml`, `src/wellman/__init__.py`,
`README.md`, `CHANGELOG.md`, `tests/test_cli.py`, and `uv.lock`) to `0.23.2` so
the Validator-merged `ticket-109` (`new-project 0.20.162` adoption), `ticket-111`
(lease phases and legacy worktree records), and `ticket-112` (skip foreign
`*worktree-lease/vN` records in `authority-lifecycle`) fixes are released together.

## Acceptance criteria

- [ ] AC-01: `pytest -q` passes at `0.23.2` with version consistency across `VERSION`,
      `pyproject.toml`, `wellman.__version__`, and `wellman --version`.
- [ ] AC-02: `./project/governance-check.sh --base origin/main` and `wellman check` pass.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
