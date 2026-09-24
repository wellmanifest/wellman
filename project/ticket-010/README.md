# Ticket 010: Validate published Docs adoption pins

- **ID**: ticket-010
- **Owner**: codex-docs-compat
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-09-24

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: the user requested execution and merge of the remaining C2004/Wellman repairs on 2026-09-24. C2004 correctly pins published Docs 0.5.0, while Wellman only accepts an older revision. Preserve immutable pins, repository binding and fail-closed checks; support the verified published policy without forcing an adopter downgrade. Source changes are restricted to the two paths in intent.json. Publication uses the declared independent Validator.

## Acceptance criteria

- [x] AC-01: Current and legacy published revision/digest pairs pass; mismatched or unknown records fail.
- [x] AC-02: Full tests and governance pass; the exact C2004 Docs adoption validates without changes to C2004.

Validation: 116 tests passed. The C2004 adoption now has zero Docs findings; its separate missing manifest remains visible. Published policy bytes were read from wellmanifest/docs at aa92136b4e94f48355c39fb206286aba024c6aa4 and match af5fde2d52e1c292e569cd47a4068f0e42181a8f8fb9fc21737a569bee9a206f.
