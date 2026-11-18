# Ticket 108: Release wellman 0.23.1 with the idleTakeover-compatible checker

- **ID**: ticket-108
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-18

## Goal and scope

Owner request (2026-11-18): stop the standards from producing errors that make
no sense. The released wellman 0.23.0 bundles a governance checker that rejects
the optional `coordination.idleTakeover` policy. Every repository adopted from
wellmanifest/new-project 0.20.15x therefore fails `wellman check` with
`GOV-MANIFEST-001`. semcod/monag, semcod/diagit and subactor/reflex all failed
on 0.23.0 and pass on `main` (05d2b48).

The fix is already merged (ticket-104), as is ticket-106. This ticket bumps the
coupled release metadata to 0.23.1 and records both fixes in the changelog, so
the release can be tagged and published.

## Acceptance criteria

- [ ] AC-01: `PYTHONPATH=.:src pytest -q tests/test_cli.py` passes at 0.23.1.
- [ ] AC-02: `./project/governance-check.sh` and `wellman check` pass.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
