# Ticket 024: Make fleet adoption plans disclose local CI recovery policy effects

- **ID**: ticket-024
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-10-04

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: the user requested applying Wellmanifest
billing-block recovery standards through Wellman across projects. Correct
fleet planning before a broad rollout: every additive policy, standard pack
and host instruction effect must be disclosed. Apply must honor that plan,
preserve existing restrictions and native pins, and reject stale plans before
writing. Do not change billing, deployed controllers, protected checks or
unrelated fleet targets in this implementation ticket.

Allocation created this canonical checkout and its exclusive ticket lease,
then index generation failed because /tmp has no free space. Preserve the
allocated ticket and use repository-local temporary storage for subsequent
checks; do not allocate another ticket or delete unrelated data.

## Acceptance criteria

- [x] AC-01: Plans disclose requirements, local-CI policy, pack and all missing host files.
- [x] AC-02: Apply performs only planned writes; stale or unsafe plans fail
  before repository mutation and preserve existing policy and native pins.
- [x] AC-03: All 195 tests and managed governance pass locally. The complete
  suite used bwrap with a private /tmp and an explicit /dev binding, preserving
  the full host /tmp and avoiding fixture discovery into the delivery checkout.
- [ ] AC-04: Independent exact-head validation, protected merge and installed
  version readback. Wellman issue #28 tracks this candidate. OneDev profile
  enrollment #491 and Validator check-policy migration #609 are separate
  prerequisites; the current preflight is configuration-only and still names
  hosted governance contexts. No local check has been represented as approval.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
