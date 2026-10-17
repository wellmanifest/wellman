# Ticket 061: Fix false deployment profile inference, add stdlib AST module analysis fallback, and wire fleet parameters

- **ID**: ticket-061
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-17

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: continue analysis, repairs, and standard alignment across projects using `wellmanifest/wellman`.

1. Fix false `deployment` profile inference in `src/wellman/adoption.py`: do not infer the `deployment` profile solely from default `wellmanifest/new-project` `.governance/manifest.json` boilerplate (`docker.required: false`, `dockerfiles: ["Dockerfile", "Dockerfile.e2e"]`, `composeFiles: ["compose.yml", "compose.yaml", "docker-compose.yml", "docker-compose.yaml", "compose.e2e.yml"]`) when none of those files exist on disk, while continuing to infer `deployment` when `docker.required: true`, custom non-default paths are configured in `manifest.json`, or any deployment file exists on disk.
2. Add a pure-Python stdlib `ast` module analysis fallback to `_MODULE_ANALYSIS` in `src/wellman/adoption.py` when `code2llm` is not installed in the isolated `-I` interpreter, and expand `recommend()` import heuristics (`korullm`, `mcp`, `fastmcp`, `redup`, `prefact`, `koru`, `pfix`, `pactfix`, `heal`, `uncrash`, `taskand`, `uriprocess`).
3. Wire `repository_name` in `sync_agent_instructions` and `queue_name` / `engine_runner` in `trigger_taskand_execution` in `src/wellman/fleet.py` to eliminate `PERF-AUDIT-KWARG-001` unused-parameter findings.

## Acceptance criteria

- [x] AC-01: Default `new-project` `.governance/manifest.json` with `docker.required: false` and absent default Docker/Compose files does not falsely infer the `deployment` profile.
- [x] AC-02: `recommend(root, analyze=True)` succeeds via stdlib AST module scanning when `code2llm` is absent in `-I` mode while preserving `ProjectAnalyzer` execution and failure handling.
- [x] AC-03: `sync_agent_instructions` and `trigger_taskand_execution` wire `repository_name`, `queue_name`, and `engine_runner` with regression tests.
- [x] AC-04: All unit tests and `./project/governance-check.sh` pass.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
