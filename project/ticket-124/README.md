# Ticket 124: Place managed standards-ssot block at top of AGENTS.md for small-LLM primacy

- **ID**: ticket-124
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-23

## Goal and scope

Place the managed `<!-- wellmanifest:standards-ssot:start ... -->` block right after the leading H1 heading (or at byte 0 if no H1) in `src/wellman/host_agent_sync.py` and migrate any legacy bottom-placed block to the top so every LLM—including smaller/faster models—sees the hard `.worktrees/` storage invariants and live `STANDARDS.md` index in the first 20 lines rather than buried at byte 18,000.

Execution authorization: `SESSION_EXECUTION_AUTHORIZATION` granted by direct user request ("kontynuuj").

## Acceptance criteria

- [x] AC-01: `_place_block_at_top()` removes any existing SSOT block and inserts the updated block immediately after a leading `# ` heading (or at byte 0).
- [x] AC-02: Existing prose (such as Windsurf's `global_rules.md` or legacy workspace rules) is preserved cleanly with zero duplicate SSOT markers.
- [x] AC-03: `tests/test_host_agent_sync.py` verifies top placement (`offset < 100`) and single-block migration on a large `AGENTS.md`.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
