# ticket-037 Preflight pinned analyzer environments and separate explicit tool updates

- **ID**: ticket-037
- **Owner**: agent:codex-stage1
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION

SESSION_EXECUTION_AUTHORIZATION: User says “wykonuj kolejne zadania, sclaaj, testuj”. Execute planfile://wellman-stage1/PLF-008, run required tests and invoke independent protected review and merge.

- [x] AC-01: Read-only version/sumr checks, isolated exact-pin updates, failure-preserving stamps and unknown/symlink storage protection.
- [ ] AC-02: Full tests and accepted-base managed gate pass; independent protected exact-head approval and merge.

Deliver read-only pinned tool/sumr preflight and an explicit separate environment update command whose success stamp is written only after isolated environment verification, exact installation, postflight and lock persistence; protected independent review and merge.

Validation: 496 full tests pass, including 30 environment cases for missing/unsupported tools, sumr entrypoint, exact pins, isolated-prefix guard, installation/postflight/write failures, bounded locks, serialized updates and process-group timeout/output limits.
