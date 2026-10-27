# Ticket 076: Enforce baseline standard prerequisites for worktrees, tickets, git-lifecycle, agent hosts, and logs

- **ID**: ticket-076
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-27

SESSION_EXECUTION_AUTHORIZATION: User explicitly requested verification and remediation of wellmanifest/* standard initialization and enforcement in wellman.

## Goal and scope

Ensure `wellman check` and `StandardsValidator.validate_required_standards()` fail closed when a locked repository declares `wellmanifest/new-project`, `wellmanifest/worktrees`, `wellmanifest/ticket-lifecycle`, or `wellmanifest/git-lifecycle` in `.governance/standard-requirements.json` without having migrated its scaffold to install the required artifacts (`project/governance-check.sh`, `worktree-guard.yaml`, `.subactor/manifest.json`, `project/new-ticket.sh`, `project/TICKETS.md`, `.githooks/pre-commit`). Also implement `check_logs()` for `--standard wellmanifest/logs` and wire registered standard checks (`wellmanifest/mcp`, `wellmanifest/hostguard`, `wellmanifest/uriprocess`, `wellmanifest/modularity`, `wellmanifest/priority`) into `ConformanceRunner.run_all()`.

## Acceptance criteria

- [x] AC-01: `StandardsValidator.validate_required_standards()` reports `GOV-NEW-PROJECT-INCOMPLETE`, `GOV-WORKTREES-INCOMPLETE`, `GOV-TICKET-LIFECYCLE-INCOMPLETE`, and `GOV-GIT-LIFECYCLE-INCOMPLETE` when a locked adoption is missing those required artifacts.
- [x] AC-02: `ConformanceRunner.run_standard("wellmanifest/logs")` executes `check_logs()` instead of returning `GOV-STANDARD-NOT-IMPLEMENTED`.
- [x] AC-03: `ConformanceRunner.run_all()` executes `check_mcp`, `check_hostguard`, `check_uriprocess`, `check_modularity`, and `check_priority` when registered in `.governance/standard-requirements.json`.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
