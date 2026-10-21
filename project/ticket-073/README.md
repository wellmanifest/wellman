# Ticket 073: Enforce project-owned report and operational evidence placement

- **ID**: ticket-073
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-10-21

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: the user explicitly requests correcting enforcement of wellmanifest/report, logs, docs and worktrees through Wellman, so project data is not stored in unrelated agent-global folders. Implementation, tests and protected publication are authorized. This is task consent, not independent writer or merge authority.

Use exactly the allocated CLI, CLI-test, documentation and index paths. Heyasa PLF-013 records intake; preserve Heyasa ticket015 and PLF010/012. Source investigation confirms that aggregate Docs checks validate adoption/index only; no pinned prepare/complete consumer exists. A generic external receipt is not a canonical report.

## Acceptance criteria

- [x] AC-01: Wellman rejects external, traversal, symlink and foreign-worktree deliverable paths before its writes; preserves declared cross-repository ownership.
- [x] AC-02: Pin-verified Docs prepare/complete integration rejects missing results, private-recovery-only reports and failed final checks; meaningful positive/negative CLI regressions and governance pass.
- [x] AC-03: Documentation explains report manifests versus raw Logs evidence and preserves actual ownership; protected publication/readback are recorded separately.

## Admission and next action

The user explicitly authorized one additional admission on 2026-10-21. The protected controller is healthy under policy 1960dccab58574b935254f93493c834383660eb1403a035279a8050e1bdca016 and returned workspace_write for this exact ticket, intent, scope, owner and base. Authenticated acquire/check passed: lease lease-468ada275d26b5b1eb80aa9d35df1e52, revision 2, fencing 50. The admission expires at 2026-10-21T11:06:57.009915+00:00; the editing lease has its own shorter lifetime and must be checked/renewed with current CAS values before effects. No merge/review authority was granted.

The original 23-record deployment could not restart because an expired, cancelled Willbench002 record referenced a path later replaced by a symlink. Its exact record and previous policy were archived; no branch, worktree, lease or historical data was deleted. Twenty-two unrelated records were retained and one Wellman073 record added. WIP limit8 remains unchanged because it had free capacity. Operational evidence lives in this repository's .subactor/receipts/ticket-073-artifact-placement; protected controller configuration remains under its service owner. Next: implement the bounded CLI gate and regression tests, then obtain independent publication.

## Existing evidence correction

The prior agent-global autonomy evidence directory was moved, without changing file bytes, to subactor/docs/.subactor/recovery/autonomy-admission-20261021. The migration receipt records SHA-256 for every file. This is private recovery, not published canonical documentation. The intended cross-repository report belongs at subactor/docs:architecture/analysis/heyasa-dockuri-admission.md and must follow that repository's governed document delivery.

## Implementation and verification (2026-10-21)

The CLI now delegates explicit preparation/completion to a byte-pinned Docs package, rejects external/traversal/symlink/foreign-checkout artifact paths, writes preparation receipts only under the owning project, and fails aggregate checks for undeclared completion. The final documentation is docs/information/artifact-placement.md, indexed in docs/README.md. This is bounded consumer enforcement, not an arbitrary-shell sandbox or deployment.

The S-budget declaration was narrowed from two public interfaces to one CLI boundary; no paths or objective were expanded. The prior owned lease was cancelled through the deployed controller CAS and re-acquired against the corrected intent hash cf3471326b6b3cfba87aa57586df95e3bff8918270f27a12db1260030fbdb376, fencing51. Earlier admission pins above remain historical. Current authoritative evidence is acquire-narrowed.json under the project receipts directory.

Validation: managed governance PASS; full pytest807 passed/34 skipped; final CLI regressions141 passed/8 skipped. Real Docs revision f4cb34926d7369d74b0a1fe09e896a35b72c016c pilot produced prepare0/missing-report1/complete0 and explicit publication_verified=false. The first pilot mistakenly imported the installed older Wellman; it was corrected by selecting this worktree source before testing.

Publication is still pending. Keep this ticket IN_PROGRESS until the independent controller records closure.
