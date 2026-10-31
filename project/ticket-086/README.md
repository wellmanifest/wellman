# Ticket 086: Optional Rust for operational multipacks

- **ID**: ticket-086
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-10-31

## Goal and scope

Allow one shared Python, Node or Rust core in the candidate family contract. Rust acceleration is optional; retain exact version and operation coverage and reject duplicate or inconsistent core declarations.

## Acceptance criteria

- [x] AC-01: Python/Node families without Rust validate; inconsistent and duplicate cores fail; existing Rust families remain valid.

## Session authorization

SESSION_EXECUTION_AUTHORIZATION: user requested reusable Python/npm operational multipacks with optional Rust and protected merging.

## Validation

30 multipack and registry tests passed. Managed governance: PASS.
