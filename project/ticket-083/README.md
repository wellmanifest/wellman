# Ticket 083: Validate portable operational multipack contracts

- **ID**: ticket-083
- **Owner**: agent:codex (user-requested session)
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-31

## Goal and scope

Implement an offline, non-executing validator for a candidate uriprocess multipack contract: one capability, versioned operations, shared Rust/Python/npm bindings and explicit process adapters. No registry publication or network execution. Canonical standard changes require a separately admitted standards checkout.

## Acceptance criteria

- [x] AC-01: Reject ambiguous operation/binding references, invalid effects and incompatible artifact declarations.
- [x] AC-02: Validate one contract across Rust, Python, Node and URI process declarations without executing entries or fetching dependencies.
- [x] AC-03: Provide machine-readable findings, strict schema, and meaningful positive/negative tests.

## Session authorization

SESSION_EXECUTION_AUTHORIZATION: User requested implementing Wellman first, reassessing names and extending standards for reusable operational multipacks. This ticket covers only the Wellman validation slice.

## Naming decision

Multipack is an artifact family, not an execution framework. Prefer extending wellmanifest/uriprocess over a competing wellmanifest/uripack standard. Product candidate: dockuri/uri-netprobe (network probes); final product name remains undecided. Existing uripack is an extraction tool, uriloop is orchestration, taskand is capsule execution.

## Validation and handoff

- Targeted tests: operational multipack schema and cross-binding invariant tests pass.
- Managed governance gate: PASS.
- Full suite: collection fails in existing applicability.py because registry data-plane has no CAPABILITIES mapping. Neither file is modified by this ticket.
- Remaining: independently admitted canonical URIprocess profile extension; main Wellman CLI integration; runtime parity tests; immutable release provenance and per-platform build matrix; publication through protected delivery.
- Canonical URIprocess checkout contains unknown untracked governance files and lacks managed work_start_check.py; preserved without modification.
