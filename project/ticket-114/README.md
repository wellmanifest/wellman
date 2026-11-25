# Ticket 114: Add wellman advise: standard-grounded next steps with optional oqllm/SubLLM advice

- **ID**: ticket-114
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-21

## Goal and scope

To be completed from human-owned input.

Requested by the owner on 2026-11-21: Wellman should say what to do next and
use oqllm (SubLLM) when a language model is needed. Proposed scope (pending
owner approval):

- `src/wellman/advise.py` and `wellman advise [--root] [--llm auto|off] [--json]`
  (`src/wellman/cli.py`): one `wellman.advice/v1` report per repository.
  - Conformance findings become ordered next steps with their remediation.
  - Each unfinished ticket lease gets a standard-grounded decision: `settle`
    when the adopted terminal controller plans a verified release and every
    ignored entry is safe runtime state per the adopted governance classifier
    (`.governance/prune_merged_worktrees.py`, digest-verified); `owner-review`
    for unclassified ignored data; `keep` for changes, unmerged heads or
    unplanned leases; `owner-cancel-or-handoff` for a missing worktree whose
    lease is older than 7 days. Each cites its standard and rule.
  - Only items no rule decides go to a model: the loopback oqllm gateway
    (OpenAI-compatible, up to three routed models) or the SubLLM client. The
    answer is attached as `llm_suggestion` (`advisory: true`) and never
    changes a decision.
  - With `URTLOG_STATE_DIR`, the advice is recorded as an advisory audit event
    in uritime-urtlog (`proc://wellman/advise/standards`).
  - Read-only: nothing is executed or written in the repository.
- `tests/test_advise.py`: decisions, active-lease cap, transport fallback,
  loopback guard, rendering, opt-in urtlog.

Live check on paxlet-com/heyasa: 14 `settle`, 12 `owner-cancel-or-handoff`;
oqllm (`glm-5.2`) answered the advisory request.

## Acceptance criteria

- [ ] AC-01: Scope is approved by a human owner.
- [ ] AC-02: `wellman advise` lists next steps with standard references.
- [ ] AC-03: A model is called only for undecided items and cannot change a
      decision; oqllm is loopback-only with SubLLM fallback.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.

<!-- ticket-radar:start -->
## Ticket Radar

Initial planned-scope estimate; advisory only, not execution or merge approval.

| Measure | Initial assessment |
| --- | --- |
| Impact score | 52/100 |
| Complexity | M |
| Estimated effort | 54 min |
| Planning budget | 30 min |
| Split recommended | yes |

Diagnostics: RADAR-ACCEPTANCE-MISSING, RADAR-BUDGET-EXCEEDED.
<!-- ticket-radar:end -->
