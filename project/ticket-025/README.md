# Ticket 025: Structure-aware standard recommendations

- **ID**: ticket-025
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION

SESSION_EXECUTION_AUTHORIZATION: user requests Wellman to select/update appropriate standards using code2llm AST and SubLLM analysis, with regix, prefact, glon, goal, code2logic, redup, doql, sumd and code2docs as supporting evidence tools. Continue protected publication under the existing session request.

- [x] AC-01: Bounded AST analysis distinguishes libraries, CLI tools and services; deterministic recommendations and optional catalog-constrained SubLLM advice retain evidence. New standards remain proposals. No implicit target writes.
- [x] AC-02: Additive registration preserves adoption pins; full tests, real code2llm smoke examples and governance pass before protected publication.

Fleet version/pin updates use existing plan/apply and the pinned adopter. This ticket does not mutate arbitrary repositories or protected CI policy.

## Validation and publication

- Full Wellman suite: 210 tests passed; managed governance PASS.
- Real static Code2LLM smoke: Wellman and Code2Docs; Code2Docs retains baseline, no service profile.
- SubLLM dependency: subactor/subllm ticket-117; 156 policy/resolver/config tests and 575 full tests passed.
- Live advice remains unavailable (CompletionError); deterministic analysis and unavailable-state reporting work. No successful live LLM verdict is claimed.
- Fleet selection is bounded and read-only. New standard proposals are advisory; no unreviewed fleet or protected pin update was applied.
- Protected review/merge pending.
