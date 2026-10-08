# Ticket 026: Bounded Code2LLM module evidence

- **ID**: ticket-026
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-10-08

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: user requested implementation, tests and protected publication of project-specific AST-based selection in Wellman. Live matrix found seven large projects blocked by full graph JSON exceeding 20 MiB. Fix generated evidence without weakening imported-input bounds or modifying analyzed repositories.

## Acceptance criteria

- [x] AC-01: Fresh analysis serializes module evidence only, remains timeout bounded and does not execute target code or enable target caches.
- [ ] AC-02: Full tests and governance pass; repeat all ten requested project analyses and obtain protected review/merge.

## Validation

212 tests passed; managed governance passed. External matrix `artifact:wellman-ticket026/compact-requested-projects-analysis.json`: all ten projects analyzed in 7.09 seconds total, versus 3/10 successful and 45.24 seconds in the preceding full-graph series. Same module counts on the three earlier successful projects. These are single-series wall times, not a statistical benchmark. Protected review/merge remains the next effect.
