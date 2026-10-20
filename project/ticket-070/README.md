# ticket-070: Preserve actor-ci compatibility in the full Wellman CLI

- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Agent**: codex

SESSION_EXECUTION_AUTHORIZATION: the user requests continued fixes, tests and protected merges. This is the canonical CLI compatibility slice of new-project#501, following the separate governance namespace in new-project#502. Existing retained worktrees and legacy branch ticket-017 are preserved; no competing active writer or scope is admitted by the work-start report.

- AC-01: Explicit `wellman check --actor ci` delegates only to a separately installed, identity-checked governance runtime under isolated Python; exact root/base/head, output and exit code are preserved. Missing or mismatched runtime and ambiguous argument combinations fail before execution. Existing aggregate checks and `wellman run` remain available.
- AC-02: Affected and full native tests, governance and independently protected verification qualify the exact head before Validator publication. Global CLI and worker enrollment are separate effects.

Validation uses this checkout's isolated `.venv` and ignored project scratch,
launched through the already approved canonical Wellman execution implementation.
The initial dependency-light suite passed 778 tests with 34 optional skips;
after installing the same Planfile 0.1.126 wheel used by the protected OneDev
profile (SHA-256 `87e96ee45ddc5fd06b6e54a39f6dad9eea5d9a64a95d0a557a7319ed05a5f8c9`),
the full native suite passed 842 tests without skips. Two additional empty-range
negative cases and their validation fix were then qualified in the final affected
suite: 150 passed. The final protected full run must include all 844 cases.
Governance reports zero errors/warnings and `git diff --check` passes.

These observations are local qualification, not approval. Independent exact-head
OneDev verification and Validator publication remain pending; no global executable,
protected runtime pin or worker profile has been replaced.
