# Ticket 057: release 0.20.46 with ssot and semver registration

- **ID**: ticket-057
- **Owner**: claude
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-13

## Goal and scope

Release projection so the installed `wellman` CLI learns `wellmanifest/ssot`
and `wellmanifest/semver` (ticket-056, #57). PyPI already has 0.20.45
(uploaded 2026-10-04) while `main` declared 0.20.38, so this release is
0.20.46: `VERSION`, `pyproject.toml`, the `__version__` fallback and the
`uv.lock` entry (was 0.20.37) all declare 0.20.46; CHANGELOG gets the release
section. Publication follows the merge via `goal -a --delivery-mode
publish-only`; `uv tool upgrade wellman` then updates the host CLI.

SESSION_EXECUTION_AUTHORIZATION: user selected "Wydanie wellman" from the remaining tasks.

## Acceptance criteria

- [x] AC-01: all version carriers declare 0.20.46.
- [x] AC-02: test suite and `./project/governance-check.sh` pass.

## Tracking boundary

This directory contains the minimal reviewed intent.
