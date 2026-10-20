# Ticket 068: Project execution contract

- **ID**: ticket-068
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-20

## Authorization and scope

SESSION_EXECUTION_AUTHORIZATION: the user requests correction of Wellmanifest/Wellman standardization and enforcement of project-associated execution paths. Document ticket-067's reviewed launch behavior in this standard/runtime's indexed documentation. Keep implementation in its application-owned ticket; preserve the independently owned new-project workstream and protected publication.

## Acceptance criteria

- [x] AC-01: Define local execution cwd, .venv, explicit same-project primary reuse, private ignored scratch and source/result receipt ownership. Explain static/runtime and source/deployment distinctions and legacy package collision.
- [x] AC-02: Document actual positive/negative qualification, index the profile, validate metadata/links and pass the managed governance gate.
- [ ] AC-03: Retain exact source and request independent publication, binding the exact ticket-067 candidate reference.

## Proposal and validation boundary

This is an independently reviewable proposed contract, not runtime adoption. Reference the exact ticket-067 candidate and PR rather than requiring that implementation to be merged before the proposal can be reviewed. The document does not install the launcher, mediate commands or assert fleet enforcement. Runtime publication remains blocked by the genuine OneDev dependency environment tracked in onedev-agent#600; this proposal grants no bypass.

The initial three-file XS plan was narrowed by removing the optional root README change. Only the profile and docs index remain, within the two-file XS budget. No policy limit was enlarged. Document JSON frontmatter and its index link pass, and the diff is whitespace-clean.
