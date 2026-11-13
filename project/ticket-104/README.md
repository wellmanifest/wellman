# Ticket 104: fix wellman bundled governance idleTakeover compatibility

- **ID**: ticket-104
- **Owner**: agent:opencode
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-13

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: continue the user-requested correction and
protected publication. Update only Wellman’s bundled governance checker to
accept the already-canonical, schema-valid `coordination.idleTakeover` policy,
and test valid and invalid policy bounds. Keep policy semantics and canonical
`wellmanifest/new-project` source unchanged.

## Acceptance criteria

- [x] AC-01: bundled checker accepts enabled idleTakeover (15 minute idle, 120 minute lease) and rejects malformed/out-of-range values
- [x] AC-02: `tests/test_governance_check.py` + `tests/test_cli.py` pass: 150 passed, 8 skipped; `wellman check --root <schema-valid adopted repository> --json` valid; `sync_bundled.py --check` and changed-file governance pass.
- [ ] AC-03: protected PR is merged by the independent Validator

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
