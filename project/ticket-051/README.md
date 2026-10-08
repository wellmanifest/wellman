# Ticket 051: Runtime error feedback and standard selection

- **ID**: ticket-051
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-08

## Goal and scope

User-authorized PLF-3000 slice: use structured runtime failures to improve standard recommendations. Register nohardcode, taskand, uriprocess and nl-uri-dsl-llm without inferring conformance or execution authority. Add bounded data-only feedback API/CLI, recurrence grouping and explicit verification limitations. Parent retains controlled remediation execution and rollout; this slice does not claim a fully autonomous repair daemon.

## Acceptance criteria

- [x] AC-01: New standards require confirmed capabilities; feedback rejects malformed, stale-window or tampered events, deduplicates replays and records recurrence without executing log contents.
- [ ] AC-02: Focused/full tests and governance pass; independent Validator approves the current candidate before merge.
- [ ] AC-03: Installed merged tool audits real Willmux logs with honest coverage and verification states.

## Usage

`python -m wellman.runtime_feedback --help` describes explicit input paths, pinned contract digest, window, stream and subject prefix. Rules map exact diagnostic codes to registered standards; missing rules remain unclassified and are reported. Repeated scans reproduce stable group identifiers. No effect is authorized by a report.

## Local validation

131 focused tests passed. Full regression suite: 749 passed in 72.60 s using a dedicated system-temporary fixture directory. Governance: 0 errors, 0 warnings. Real Willmux JSONL: 232 structurally valid hash-chained events; session-scoped historical window groups 86 failures into two recurring codes. The current one-hour window is empty and telemetry freshness remains explicit. Independent publication and installed merged-tool canary remain pending.
