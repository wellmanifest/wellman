# Ticket 126: Verify deployment descriptor and exact binding evidence offline (PLF-012)

- **ID**: ticket-126
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-23

## Goal and scope

The previous targeted check accepted projects without deployment.json. Add offline inspection of the canonical descriptor, independent inventory lookup name and exact bytes. The public module can run while the ordinary Wellman adapter path remains reserved by a separate writer.

## Acceptance criteria

- [x] AC-01: Reject absent and malformed contracts, accept both canonical examples, match external binding reference and digest, and distinguish static verification from deployment authority.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.

<!-- ticket-radar:start -->
## Ticket Radar

Initial planned-scope estimate; advisory only, not execution or merge approval.

| Measure | Initial assessment |
| --- | --- |
| Impact score | 64/100 |
| Complexity | L |
| Estimated effort | 69 min |
| Planning budget | 30 min |
| Split recommended | yes |

Diagnostics: RADAR-ACCEPTANCE-MISSING, RADAR-BUDGET-EXCEEDED.
<!-- ticket-radar:end -->
