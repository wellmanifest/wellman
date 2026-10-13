# Ticket 056: register wellmanifest/ssot and wellmanifest/semver as reference-only standards

- **ID**: ticket-056
- **Owner**: claude
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-13

## Goal and scope

Adopting the standards in semcod/fixos on 2026-10-13, `wellman adopt auto
--standard wellmanifest/ssot` and `--standard wellmanifest/semver` failed with
`Unknown standard`, so neither could be registered or checked. Both are
published (ssot 91c894b, semver 432b6f9) and are declarative packs without a
runtime, like nohardcode and uriprocess.

Add both as `reference-only` / `S0` StandardPack entries with their schemas,
aliases `ssot` and `semver`, and applicability capabilities
(`quality:single-source-of-truth`, `lifecycle:versioned-release`).

SESSION_EXECUTION_AUTHORIZATION: user requested fixing errors found while validating and enforcing Wellmanifest standards directly in the standards.

## Acceptance criteria

- [x] AC-01: `wellman standards` lists both (34 registered) and `adopt auto --standard` registers them; registry test added.
- [x] AC-02: full suite (759 passed) and `./project/governance-check.sh` pass.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
