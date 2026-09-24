# Ticket 009: align-planfile-ticket-export-and-koru-execution-contract

- **ID**: ticket-009
- **Owner**: gemini
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-09-24

## Goal and scope

Align standardization ticket schema with Planfile and Koru execution contracts,
ensuring seamless ingestion (`name` field, dictionary `source`, list-based stdin
stream), multi-repo target distribution, and autonomous remediation trigger via
`koru --queue --loop --queue-name governance-handoff`.

## Acceptance criteria

- [x] AC-01: `emit_standardization_tickets` produces Planfile-compliant tickets with `name`, `source`, `executor` (`kind: shell`), `inputs` (`script`), and `execution` (`queue: governance-handoff`).
- [x] AC-02: `feed_to_planfile` streams a JSON list of tickets to `planfile ticket import` to satisfy Pydantic schema validation without envelope wrapping errors.
- [x] AC-03: `feed_to_planfile` routes tickets to target repositories having local `.planfile` directories.
- [x] AC-04: `trigger_koru_execution` and `--auto-remediate` / `--koru-exec` CLI flag allow autonomous closed-loop execution through Koru.
- [x] AC-05: `_print_fleet_payload` formats string repository entries (e.g. `fleet discover`).

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
