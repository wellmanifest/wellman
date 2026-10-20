# ticket-071: Bind common Python tool caches to the checkout

- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Agent**: codex

SESSION_EXECUTION_AUTHORIZATION: the user requests continued repairs, tests and protected merges. The previous actual wheel build used pip's user cache despite project-local interpreter/TMP admission. This bounded continuation of new-project#501 binds known cache variables in the canonical implementation, without changing independently pinned worker SDK sources. Work-start reports no active writer; legacy branches and integrated worktrees are retained.

- AC-01: Direct Python children use checkout-owned persistent pip/uv/XDG caches and distinct per-run TMP. Redirected/file cache paths fail before launch. Dry-run creates no state; repeated invocations reuse cache data.
- AC-02: Affected/native tests and governance pass in the canonical checkout, then the frozen exact head receives independent verification and protected publication. No static report grants execution or merge authority.

Implementation binds `PIP_CACHE_DIR`, `UV_CACHE_DIR` and `XDG_CACHE_HOME` to
`.subactor/cache/execution/tools/` in the admitted checkout. Stable tool caches
reuse the existing directory creation boundary; every invocation retains its
exclusive UUID temporary directory. Read-only admission rejects redirected or
file cache destinations, and dry-run creates no operational directories.

Local validation: 25 affected tests and all 853 native tests pass with the normal
governance plugin, using this worktree's `.venv` and checkout-owned temporary
directory. The governance gate passes with zero errors and warnings. Evidence:
`.subactor/receipts/ticket-071/{affected,native-full,governance-edit}.log`.
Exact-head OneDev verification and independent Validator publication are pending.

This change extends known environment bindings; it is not a filesystem sandbox
or interception of every tool's private cache. Independently pinned worker SDK
sources require their own reviewed adoption; this ticket does not change them.
