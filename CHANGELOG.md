# Changelog

## [Unreleased]

## [0.20.35] - 2026-09-19

### Docs
- Update README.md

## [0.20.35] - 2026-09-19

### Docs
- Update README.md

## [0.20.34] - 2026-09-19

### Docs
- Update README.md

### Other
- Update uv.lock

## [0.20.34] - 2026-09-19

### Docs
- Update README.md

## [0.20.33] - 2026-09-19

### Docs
- Update CHANGELOG.md
- Update README.md

### Test
- Update tests/__init__.py
- Update tests/test_cli.py
- Update tests/test_registry.py
- Update tests/test_runner.py
- Update tests/test_validator.py

### Other
- Update .env.example
- Update .gitignore
- Update VERSION
- Update src/wellman/schemas/adoption-bindings.schema.json
- Update src/wellman/schemas/agent-hosts.schema.json
- Update src/wellman/schemas/agent.schema.json
- Update src/wellman/schemas/approval-evidence.schema.json
- Update src/wellman/schemas/branch-intent-reconciliation.schema.json
- Update src/wellman/schemas/change-evaluation.schema.json
- Update src/wellman/schemas/decision-record.schema.json
- ... and 32 more files


All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.20.32] - 2026-09-19

### Added
- Initial standalone release of `wellman` (Wellmanifest Unified Standards Runtime).
- Standards registry covering all 24+ Wellmanifest standards (new-project, git-lifecycle, worktrees, ticket-lifecycle, merge, validation-attestation, agent, docs, dsl, code-dsl, nl-dsl-llm, authority-lifecycle, repair-lifecycle, deployment, etc.).
- Governance profiles: `baseline`, `domain-pack`, `runtime-service`, `agent-executor`, `deployment`, `full`.
- Conformance validation engine with finding codes (`GOV-*`, `STD-PACK-*`).
- Bundled schemas directory with 38+ JSON schemas for offline verification.
- Unified CLI with commands: `standards`, `info`, `profiles`, `check`, `adopt`, `validate`, `gate`, `version`.
- Programmatic Python API for standards inspection and compliance checks.
