# Ticket 001: Wellman NVIDIA pilot hardening

- **ID**: ticket-001
- **Status**: IN_PROGRESS
- **Created**: 2026-09-19

## Goal

Run the Wellman standards-control pilot on the NVIDIA host and correct CLI
behaviour that can incorrectly report a successful adoption or conformance
check.

## Acceptance criteria

- [x] Unknown standards and profiles do not create an adoption manifest.
- [x] An existing manifest is preserved unless `wellman adopt --force` is used.
- [x] A selected standard runs its own check or returns an explicit unsupported-check failure.
- [x] Regression tests, package build, package metadata validation, and the NVIDIA-host Koru pilot pass.
