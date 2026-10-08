# ticket-036 Expose evidence selection plans and explicit backlog export through recommend

- **ID**: ticket-036
- **Owner**: agent:codex-stage1
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION

SESSION_EXECUTION_AUTHORIZATION: User says “wykonuj kolejne zadania, sclaaj, testuj”. Execute planfile://wellman-stage1/PLF-007, run required tests and invoke independent protected review and merge.

- [x] AC-01: New recommendation mode produces explained schema-valid plans and rejects stale or incompatible input before effects; legacy recommend remains compatible.
- [ ] AC-02: Full tests and managed accepted-base gate pass; independent protected approval and merge bind exact head.

Expose explicit evidence selection planning and local review backlog through the existing recommend command; preserve legacy recommend/register/fleet behavior and publish through protected independent review and merge.

Validation: 81 focused CLI tests and 464 full tests passed, including legacy recommend/register/fleet compatibility, snapshot replay, stale/artifact/symlink guards and explicit review backlog export.
