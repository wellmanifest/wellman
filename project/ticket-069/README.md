# Ticket 069: Local scratch scanner and native backlog regressions

- **ID**: ticket-069
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-20

## Authorization

SESSION_EXECUTION_AUTHORIZATION: the user requested continued repair of Wellmanifest/Wellman path ownership and logical enforcement errors. Full qualification in ticket-067's actual local environment with exact Planfile 0.1.126 exposed two existing failures (829 passed, 2 failed): the scanner filtered absolute ancestor names and silently ignored all files in canonical worktrees/local scratch; an owned-ticket fixture used unsupported status active rather than native in_progress.

Implement the bounded scanner correction and preserve the owned-ticket assertion with the valid native status. Extract the scanner from the existing oversized URI module instead of expanding it. Do not change the Planfile pin, add skips or manufacture protected verification. The independent OneDev dependency prerequisite remains onedev-agent#600.

## Acceptance criteria

- [x] AC-01: Scan owned source below ignored ancestor names, prune ignored descendants before traversal, and refuse symlinked source inputs without reading them. Preserve the URI scanner response and actual invalid-URI findings.
- [x] AC-02: Real affected suites with Planfile 0.1.126 and local scratch pass, including preservation of active/claimed native backlog records and scanner traversal negatives; managed governance passes.
- [ ] AC-03: Publish a reviewable bounded candidate and retain exact qualification, independent review and deployment status separately.

## Qualification

All 39 affected cases pass through the candidate project-bound launcher with Planfile 0.1.126 installed in this checkout's own .venv. Scratch and receipts stay below this checkout. The real scanner regression checks ignored ancestors, ignored descendant pruning, invalid-URI findings and symlinked file/directory exclusion. The native owned-ticket preservation assertion is unchanged apart from using the supported in_progress status. The managed governance gate passes. Extracting the scanner reduces uri.py from 552 to 482 lines; the scanner module is 78 lines.
