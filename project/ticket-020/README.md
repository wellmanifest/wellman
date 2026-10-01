# Ticket 020: Preserve package ownership when adopting Docs

- **ID**: ticket-020
- **Owner**: codex
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-10-01

## Goal and scope

Fix fleet Docs adoption inserting an undeclared file into new-project's managed
lock, which breaks the package-target invariant. Preserve package-owned locks;
refresh only a pre-existing Docs entry in a legacy lock without a package map.
The plan must describe the same lock effects as execution.

## Acceptance criteria

- [x] AC-01: Regression tests cover mapped locks and legacy tracked/untracked Docs.
- [x] AC-02: Fleet/adoption tests and the managed governance gate pass.
- [ ] AC-03: Publish and merge through exact-head independent protected delivery.

## Tracking boundary

Minimal scoped intent; no runtime upgrade is claimed before protected publication.

## Validation

70 adoption/fleet tests passed, including six lock ownership regressions.
The managed governance gate passed with zero errors and warnings.
