# Ticket 016: fleet-planfile-strategy-and-cicd-subtasks

- **ID**: ticket-016
- **Owner**: gemini
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-09-28

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: user requested adding execution strategy and linked CI/CD subtasks to fleet standardization tickets.
1. Add structured execution strategy to standardization tickets (`strategy: { phases: ["remediation", "verification", "git_delivery"] }`).
2. Add linked CI/CD verification and delivery subtasks with `parent`, `children`, and `blocked_by` relationships.
3. Include `.governance/manifest.lock.json` generation and clean git commit in the autonomous remediation script.
4. Update unit test suite in `tests/test_fleet.py`.

## Acceptance criteria

- [x] AC-01: `emit_standardization_tickets` produces execution strategy and linked CI/CD subtasks for each repo finding.
- [x] AC-02: Autonomous remediation script handles lockfile generation and clean git commit.
- [x] AC-03: Full `pytest tests/test_fleet.py` passes cleanly.
- [x] AC-04: `./project/governance-check.sh` passes cleanly (GOV-PASS).

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.

