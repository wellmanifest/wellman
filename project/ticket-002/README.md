# ticket-002: Complete automatic standards registration and self-adoption with repository-local path safety

- **Status**: DONE
- **Workflow state**: DONE

## Recovery boundary

Existing work registered through the fenced local allocator.
This is not retrospective validation or protected merge approval.

## Acceptance criteria

- [x] AC-01: Preserve additive registration and reject ambiguous or escaping write roots; cover nested directories, linked worktrees, explicit non-Git bootstrap and symlinks.
- [x] AC-02: Complete immutable self-adoption, native ticket recovery, package metadata and managed governance validation.
- [x] AC-03: Verify the built artifact and a bounded rollout canary before protected publication; do not equate registration with enforcement.

Validation: 74 product tests pass with the managed pytest governance gate;
exact-base governance reports zero errors and warnings. Lock verification,
sdist/wheel build and Twine checks pass. An isolated wheel installation verifies
nested-root selection, no-write preview, idempotence and symlink rejection.
Protected PR review, merge, release and global runtime installation remain
publication stages; none is implied by these local test results.

## Session authorization and continuation

SESSION_EXECUTION_AUTHORIZATION: the user requested continued Wellman adoption,
repository-local path correction, and explicitly approved controller handoff of
this existing ticket. Recovery used published new-project v0.20.36 at
368085282d0caa41cfa5ef2ec65644920566ae77 after protected PR #388 merge.
The previous registration implementation and bootstrap snapshot are preserved.
Current integration scope combines that self-adoption with the requested CLI
path correction; other repositories require their own admitted owner and lease.
Additional catalog checkers and broad real-repository rollout remain separate
follow-up work, not conformance claims from this registration slice.

Review remediation: continue under the user's publication authorization with
new-project 0.20.38 at e2fd653ff801fb228fca818e1d874ee685a4da62, independently
approved and merged in upstream PR #390. Adopt only its published immutable
release through the managed updater to remove the unsafe review-bypass
guidance identified in PR #3. Retest and obtain fresh exact-head review;
previous review progress is not approval of the updated adoption.
