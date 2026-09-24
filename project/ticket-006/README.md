# Ticket 006: Add standardization diagnostic remediation ticket export and koru handoff

- **ID**: ticket-006
- **Owner**: antigravity
- **Status**: DONE
- **Workflow state**: DONE
- **Created**: 2026-09-24

## Goal and scope

Integrate standardization error reporting from `wellman fleet check` with Planfile ticket emission and autonomous remediation delegation:
1. Provide `emit_standardization_tickets` in `wellman.fleet` to transform fleet conformance findings into actionable `planfile.tickets/v1` records.
2. Support `--koru-handoff` formatting with `governance-handoff` queue, `remediation_intent`, and `koru` executor metadata.
3. Support `--monag-triage` conflict checking via `monag` when available to prevent collision with active agent leases.
4. Expose CLI flags `--emit-planfile`, `--koru-handoff`, `--feed-planfile`, and `--monag-triage` in `wellman fleet check`.
5. Add unit and regression tests in `tests/test_fleet.py`.

## Acceptance criteria

- [x] AC-01: `emit_standardization_tickets` transforms findings into valid `planfile.tickets/v1` structure.
- [x] AC-02: `--koru-handoff` injects remediation intent and autonomous repair metadata.
- [x] AC-03: `wellman fleet check --emit-planfile` writes output to file.
- [x] AC-04: All test suites (`pytest`) and governance checks pass.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.

