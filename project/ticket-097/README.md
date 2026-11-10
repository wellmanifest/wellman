# Ticket 097: Release wellman 0.22.0 with conformance and domain-pack S1 checkers

- **ID**: ticket-097
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-10

## Goal and scope

Bump `wellman` release projections (`VERSION`, `pyproject.toml`, `src/wellman/__init__.py`, `README.md`, `CHANGELOG.md`, `uv.lock`) from `0.21.0` to `0.22.0`, consolidating S1 static conformance checkers (`conformance_checkers.py`, `domain_pack_checkers.py`), `wellmanifest/docs` `0.6.0` pin support, standard pack registrations, and `nohardcode` path scanning fixes for protected publication.

## Acceptance criteria

- [x] AC-01: Version metadata (`VERSION`, `pyproject.toml`, `src/wellman/__init__.py`, `uv.lock`, `README.md`) and `CHANGELOG.md` consistently declare `0.22.0`.
- [x] AC-02: Full test suite (`pytest`), `./project/governance-check.sh`, and `wellman check` pass cleanly.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
