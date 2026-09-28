# Ticket 018: Infer deployment profile from conventional directories and add repeatable standard CLI flag

- **ID**: ticket-018
- **Owner**: antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-09-28

## Goal and scope

Address GitHub issue #16:
- In `src/wellman/adoption.py`: Expand `deployment` profile auto-inference in `register()` to inspect conventional deployment subdirectories (`deploy/`, `deployment/`, `infra/`, `docker/`) for `Dockerfile` and Compose definitions, and declared stack profiles in `.governance/manifest.json`.
- In `src/wellman/cli.py`: Expose repeatable `--standard` / `-s` argument in `wellman adopt auto` command to allow registering individual standards directly via CLI without needing custom Python scripts.
- In `README.md`: Document `--standard` / `-s` and deployment profile inference across subdirectories.
- In `tests/`: Add comprehensive tests in `tests/test_adoption.py` and `tests/test_cli.py`.

## Acceptance criteria

- [x] AC-01: `src/wellman/adoption.py` infers `deployment` profile when `Dockerfile` or Compose files exist in conventional deployment directories (`deploy/`, `deployment/`, `infra/`, `docker/`) or declared stack profiles.
- [x] AC-02: `src/wellman/cli.py` supports repeatable `--standard` / `-s` flag for `wellman adopt auto`, passing standards to `register()`.
- [x] AC-03: `README.md` documents `--standard` and deployment directory inference.
- [x] AC-04: Full pytest test suite passes.
- [x] AC-05: `./project/governance-check.sh` passes with 0 errors and 0 warnings.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.

