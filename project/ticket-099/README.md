# Ticket 099: Implement S1 static checker for wellmanifest/python distribution parity

- **ID**: ticket-099
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-11-10

## Goal and scope

1. Promote `wellmanifest/python` (the final `S0` `reference-only` pack in
   `STANDARDS_CATALOG`) to `S1` (`local-conformance`), keeping non-authority
   `excludes` (`execution authority`, `verified runtime conformance`).
2. Implement a dependency-free, read-only static checker in
   `src/wellman/python_pack_checker.py` enforcing:
   - `PYTHON-DIST-001`: `pyproject.toml` / `VERSION` parity, newest `dist/*.whl`
     version alignment, and byte-for-byte parity between packaged wheel `.py`
     files and source modules (`build_content_differs`).
   - `PYTHON-DIST-002`: `[project.scripts]` entry-point module/callable
     existence and `--version` CLI flag contract.
   - `PYTHON-DIST-003`: wheel archive safety bounds (regular file, member count,
     uncompressed size, traversal rejection) and completeness of source modules
     in the built wheel (`build_file_missing`).

## Acceptance criteria

- [x] AC-01: `PYTHONPATH=src pytest -n auto -q` passes across the full suite, covering positive and negative `PYTHON-DIST-001/002/003` cases and confirming zero `S0` packs remain in `STANDARDS_CATALOG`.
- [x] AC-02: `wellman check --standard wellmanifest/python` passes on upstream `wellmanifest/python`, and `./project/governance-check.sh` plus `wellman check --root .` pass with zero errors.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
