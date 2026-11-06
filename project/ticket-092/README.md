# Ticket 092: Reject unverified conformance and unqualified fleet remediation

- **ID**: ticket-092
- **Owner**: codex
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-11-06

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: the user requested investigation of Heyasa
queue execution and Wellmanifest adoption, then continued with "kontynuuj,
scalaj, naprawiaj, testuj" on 2026-11-06. This authorizes these bounded source
fixes, regression tests and protected independent publication.

Reject selected conformance checks that have no implementation. Emit fleet
findings as blocked admission requests, preserving dependencies and diagnostic
context without inventing a native ticket, lease or executable authority.
Remove the unbound Taskand fallback that adopts and commits in a target checkout
even after failed verification. Preserve the explicitly supplied engine adapter.

Findings: STD-AUDIT-003 and STD-AUDIT-004 in Heyasa's external
standards-causality-20261106 report. Runtime packaging, native controller
implementation, POA receipt semantics and new-project takeover policy remain
separate owner dependencies.

The compact allocation did not require a delivery block, but the deployed
continuity checker requires its target branch. The completed contract uses the
manifest's allowed M class for the two already accepted interface corrections;
the original four-file scope, two components and zero dependencies are unchanged.

CI reconciliation within the accepted fleet scope: the protected run timed out
after 600 seconds. Profiling its native Planfile integration found 48 individual
allocations/creates followed by 48 redundant initial updates (41 seconds in one
regression). Use the pinned native batch allocator/persistence capabilities under
the same lock, establishing all dependency IDs before creation and retaining CAS
for existing proposals. This preserves verification coverage and the four-file
scope; no CI timeout or protected policy is relaxed.

## Acceptance criteria

- [x] AC-01: All ten unimplemented selected checks return an error through the CLI.
- [x] AC-02: Generated fleet requests remain blocked and contain no executable
  shell, Git commit operation or fabricated native remediation intent.
- [x] AC-03: Unbound Taskand dispatch has no subprocess or repository effects;
  dry runs report no execution and explicitly supplied adapters remain usable.
- [ ] AC-04: Regression tests and governance pass; publication uses exact-head
  independent validation.
- [x] AC-05: Initial selection export persists one native batch with resolved
  dependencies; repeat export preserves IDs, ownership and CAS behavior.

Local evidence: full suite 890 passed, 34 skipped; final affected-module suite
88 passed, 24 skipped (optional native integrations absent from the local venv).
All ten selected-check regressions also fail against the exact accepted base.
The installed native Planfile model preserves blocked admission and source
context. Import transport regressions cover central and per-repository routing,
including proposal dependencies preserved as context rather than dangling IDs.
Governance passes. Detailed logs and checkpoints are external under
`.subactor/receipts/ticket-092/`; protected publication is still pending.

After CI reconciliation: all 112 affected-module tests pass with native
Planfile 0.1.126 (162.51 seconds, no skips), and 18 bounded Testless coverage
regressions pass. The same profiled export test fell from 41.22 to 9.67 seconds.
Dependency, ownership, replay and concurrent retry tests remain enabled.
Testless proposals are advisory external artifacts; no tests were deleted.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
