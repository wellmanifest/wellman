"""Wellmanifest Standards Registry and Profile Catalog.

Unified single-source-of-truth definition for all Wellmanifest standards,
execution models, conformance levels (S0-S5), inter-standard dependency DAGs,
and adoption profiles.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class StandardPack:
    """A Wellmanifest standard pack specification."""

    id: str
    name: str
    owner: str
    description: str
    minimum_level: str = "S3"
    execution_model: str = "protected-conformance"
    owns: List[str] = field(default_factory=list)
    excludes: List[str] = field(default_factory=list)
    requires: List[str] = field(default_factory=list)
    schemas: List[str] = field(default_factory=list)
    docs_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Profile:
    """A governance composition profile."""

    name: str
    description: str
    extends: List[str] = field(default_factory=list)
    requirements: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


CONFORMANCE_LEVELS: Dict[str, str] = {
    "S0": "Versioned normative contract with closed schemas and negative examples.",
    "S1": "Dependency-free deterministic conformance command with stable finding codes.",
    "S2": "Immutable source revision and SHA-256 digests for every managed projection.",
    "S3": "The conformance command runs as a stable required CI check on pull requests.",
    "S4": "Hosted branch protection or rulesets require the exact CI check before merge.",
    "S5": "The effectful runtime validates live bindings and emits a digest-bound receipt.",
}

EXECUTION_MODELS: Dict[str, Dict[str, Any]] = {
    "reference-only": {"maximumLevel": "S0", "authorizesEffects": False},
    "local-conformance": {"maximumLevel": "S2", "authorizesEffects": False},
    "protected-conformance": {"maximumLevel": "S4", "authorizesEffects": False},
    "runtime-conformance": {"maximumLevel": "S5", "authorizesEffects": True},
}

# Catalog of all Wellmanifest standards
STANDARDS_CATALOG: Dict[str, StandardPack] = {
    "wellmanifest/nohardcode": StandardPack(
        id="wellmanifest/nohardcode", name="Configuration and hardcode detection",
        owner="wellmanifest/nohardcode", description="Policy and AST detection for hardcoded configuration and brittle runtime assumptions",
        minimum_level="S0", execution_model="reference-only",
        owns=["configuration audit"], excludes=["execution authority", "verified runtime conformance"],
        schemas=['schemas/nohardcode-policy.schema.json', 'schemas/detection-rule.schema.json'], docs_url="https://github.com/wellmanifest/nohardcode",
    ),
    "wellmanifest/taskand": StandardPack(
        id="wellmanifest/taskand", name="URI process capsules",
        owner="wellmanifest/taskand", description="Capsule contracts, grants and digital-twin gates for autonomous URI process execution",
        minimum_level="S0", execution_model="reference-only",
        owns=["capsule contracts"], excludes=["execution authority", "verified runtime conformance"],
        requires=["wellmanifest/uriprocess"],
        schemas=['schemas/capsule.v1.json', 'schemas/proc.v1.json', 'schemas/grants.v1.json'], docs_url="https://github.com/wellmanifest/taskand",
    ),
    "wellmanifest/data-plane": StandardPack(
        id="wellmanifest/data-plane", name="Authoritative Event Store and CQRS Read Model Data Plane",
        owner="wellmanifest/data-plane", description="Per-stream authoritative append-only event store, SQLite/PostgreSQL CQRS read-model indexing, low-RAM profiles, and bounded reverse-tail recovery",
        minimum_level="S3", execution_model="protected-conformance",
        owns=["event store schema", "CQRS read-model indexes", "atomic checkpointing"], excludes=["execution authority"],
        schemas=['manifest.json', 'schemas/event.schema.json'], docs_url="https://github.com/wellmanifest/data-plane",
    ),
    "wellmanifest/uriprocess": StandardPack(
        id="wellmanifest/uriprocess", name="URI process package manufacturing",
        owner="wellmanifest/uriprocess", description="Deterministic URI process package manufacture, provenance, verification and delivery",
        minimum_level="S0", execution_model="reference-only",
        owns=["package manufacture"], excludes=["execution authority", "verified runtime conformance"],
        schemas=['schemas/package.schema.json'], docs_url="https://github.com/wellmanifest/uriprocess",
    ),
    "wellmanifest/ssot": StandardPack(
        id="wellmanifest/ssot", name="Single source of truth decisions",
        owner="wellmanifest/ssot", description="Interview-first, propose-only SSOT decisions for duplicated code, configuration and vendored copies",
        minimum_level="S0", execution_model="reference-only",
        owns=["SSOT decision documents"], excludes=["execution authority", "code edits or merges", "verified runtime conformance"],
        requires=["wellmanifest/dsl"],
        schemas=['schemas/ssot-interview.schema.json', 'schemas/ssot-decision.schema.json', 'schemas/ssot-standards-lock.schema.json'], docs_url="https://github.com/wellmanifest/ssot",
    ),
    "wellmanifest/project-ssot": StandardPack(
        id="wellmanifest/project-ssot", name="Cross-Project Single Source of Truth Projection",
        owner="wellmanifest/project-ssot", description="Cross-project SSoT projection, artifact ownership contracts, and multi-repository digest synchronization",
        minimum_level="S3", execution_model="protected-conformance",
        owns=["cross-project SSoT projection", "multi-repo artifact synchronization"],
        requires=["wellmanifest/dsl", "wellmanifest/ssot"],
        schemas=["project-ssot.schema.json"], docs_url="https://github.com/wellmanifest/project-ssot",
    ),
    "wellmanifest/semver": StandardPack(
        id="wellmanifest/semver", name="Semantic versioning for heterogeneous releases",
        owner="wellmanifest/semver", description="Separate SemVer for system, host and firmware with binary identity, safe-state and OTA rollback rules",
        minimum_level="S0", execution_model="reference-only",
        owns=["release version contracts"], excludes=["execution authority", "flashing or deployment", "verified runtime conformance"],
        schemas=['schemas/embedded-release.schema.json', 'schemas/hardware-matrix.schema.json', 'schemas/pipeline-run.schema.json'], docs_url="https://github.com/wellmanifest/semver",
    ),
    "wellmanifest/nl-uri-dsl-llm": StandardPack(
        id="wellmanifest/nl-uri-dsl-llm", name="Natural language to URI and DSL",
        owner="wellmanifest/nl-uri-dsl-llm", description="Typed action URI and resource URN selection, grammar constraints and capsule handoff",
        minimum_level="S0", execution_model="reference-only",
        owns=["NL to URI contracts"], excludes=["execution authority", "verified runtime conformance"],
        requires=["wellmanifest/dsl", "wellmanifest/llm", "wellmanifest/uriprocess"],
        schemas=['schemas/process-uri.schema.json', 'schemas/conversational-process-snapshot.schema.json'], docs_url="https://github.com/wellmanifest/nl-uri-dsl-llm",
    ),
    "wellmanifest/reuse": StandardPack(
        id="wellmanifest/reuse",
        name="Code Reuse & Deduplication Standard",
        owner="wellmanifest/reuse",
        description="Cross-project code discovery, AST clone detection, declarative decision graphs, prioritized dependency chains, and streaming composition of modules, components, and processes",
        minimum_level="S3",
        execution_model="protected-conformance",
        owns=[
            "code discovery",
            "AST clone detection",
            "reuse orchestration",
            "modular extraction",
            "intent dispatching",
            "declarative decision routing",
            "prioritized dependency chains",
            "streaming module pipelines",
        ],
        requires=["wellmanifest/modularity", "wellmanifest/priority"],
        schemas=["reuse-policy.schema.json", "reuse-scan-receipt.schema.json", "stream-flow.schema.json"],
        docs_url="https://github.com/wellmanifest/reuse",
    ),
    "wellmanifest/modularity": StandardPack(
        id="wellmanifest/modularity",
        name="Structural Modularity & Boundary Standard",
        owner="wellmanifest/modularity",
        description="Deterministic module boundary contract, explicit imports/exports, acyclic dependency DAGs, and side-effect declarations",
        minimum_level="S3",
        execution_model="protected-conformance",
        owns=["module boundary contracts", "acyclic module dependency DAG", "explicit symbol exports"],
        schemas=["modularity.schema.json", "verification-receipt.schema.json"],
        docs_url="https://github.com/wellmanifest/modularity",
    ),
    "wellmanifest/priority": StandardPack(
        id="wellmanifest/priority",
        name="Lexicographic Priority & Signal Ranking Standard",
        owner="wellmanifest/priority",
        description="Declarative priority DSL, lexicographic tier ordering (floor > standard > opportunistic), signal-driven revision, and ranking receipts",
        minimum_level="S3",
        execution_model="protected-conformance",
        owns=["priority tier ranking", "signal-driven weight revision", "priority ranking receipts"],
        schemas=["priority.schema.json", "readings.schema.json", "evaluation-context.schema.json", "ranking-v2.schema.json"],
        docs_url="https://github.com/wellmanifest/priority",
    ),
    "wellmanifest/new-project": StandardPack(
        id="wellmanifest/new-project",
        name="New Project & Repository Bootstrap",
        owner="wellmanifest/new-project",
        description="Repository bootstrap, pack composition, immutable adoption projection, lockfile and manifest checks",
        minimum_level="S4",
        execution_model="protected-conformance",
        owns=["repository bootstrap", "pack composition", "immutable adoption projection"],
        schemas=["manifest.schema.json", "lock.schema.json", "standard-adoption.schema.json", "diagnostics.schema.json"],
        docs_url="https://github.com/wellmanifest/new-project",
    ),
    "wellmanifest/git-lifecycle": StandardPack(
        id="wellmanifest/git-lifecycle",
        name="Git Lifecycle",
        owner="wellmanifest/git-lifecycle",
        description="Repository identity, branch and ref lifecycle, pull-request lifecycle, remote hygiene, branch intent",
        minimum_level="S4",
        execution_model="protected-conformance",
        owns=["repository identity", "branch and ref lifecycle", "pull-request lifecycle", "remote hygiene"],
        requires=["wellmanifest/new-project", "wellmanifest/lifecycle"],
        schemas=["git-lifecycle.schema.json", "repository-initial-ref.schema.json", "repo-hygiene.schema.json"],
        docs_url="https://github.com/wellmanifest/git-lifecycle",
    ),
    "wellmanifest/worktrees": StandardPack(
        id="wellmanifest/worktrees",
        name="Worktrees Management",
        owner="wellmanifest/worktrees",
        description="Worktree placement, worktree naming conventions, lease path identity, local checkout audit handoff, overlap guard",
        minimum_level="S3",
        execution_model="protected-conformance",
        owns=["worktree placement", "worktree naming", "lease path identity", "local checkout audit handoff"],
        requires=["wellmanifest/new-project"],
        schemas=["worktrees.schema.json", "worktree-guard.schema.json"],
        docs_url="https://github.com/wellmanifest/worktrees",
    ),
    "wellmanifest/merge": StandardPack(
        id="wellmanifest/merge",
        name="Autonomous Merge Standard",
        owner="wellmanifest/merge",
        description="Divergent-work disposition, merge decision contract, merge safety fences",
        minimum_level="S4",
        execution_model="protected-conformance",
        owns=["divergent-work disposition", "merge decision contract"],
        excludes=["merge execution", "deletion"],
        requires=["wellmanifest/new-project", "wellmanifest/git-lifecycle"],
        schemas=["merge-decision.schema.json"],
        docs_url="https://github.com/wellmanifest/merge",
    ),
    "wellmanifest/validation-attestation": StandardPack(
        id="wellmanifest/validation-attestation",
        name="Validation & Attestation",
        owner="wellmanifest/validation-attestation",
        description="Trusted exact-head evidence, test attestation validation, tamper-evident test runs",
        minimum_level="S4",
        execution_model="protected-conformance",
        owns=["trusted exact-head evidence", "attestation validation"],
        requires=["wellmanifest/new-project"],
        schemas=["approval-evidence.schema.json"],
        docs_url="https://github.com/wellmanifest/validation-attestation",
    ),
    "wellmanifest/ticket-lifecycle": StandardPack(
        id="wellmanifest/ticket-lifecycle",
        name="Ticket Lifecycle",
        owner="wellmanifest/ticket-lifecycle",
        description="Ticket state semantics, transition rules, ticket execution leases, split plans, ticket activity tracking",
        minimum_level="S3",
        execution_model="protected-conformance",
        owns=["ticket state semantics", "ticket transition semantics", "ticket execution lease"],
        requires=["wellmanifest/new-project", "wellmanifest/lifecycle"],
        schemas=["ticket-lifecycle.schema.json", "ticket-execution-lease.schema.json", "split-plan.schema.json", "ticket-activity.schema.json"],
        docs_url="https://github.com/wellmanifest/ticket-lifecycle",
    ),
    "wellmanifest/authority-lifecycle": StandardPack(
        id="wellmanifest/authority-lifecycle",
        name="Authority Lifecycle",
        owner="wellmanifest/authority-lifecycle",
        description="Authority lease semantics, fencing and expiry semantics, distributed locks",
        minimum_level="S5",
        execution_model="runtime-conformance",
        owns=["authority lease semantics", "fencing and expiry semantics"],
        requires=["wellmanifest/lifecycle"],
        schemas=["change-lease.schema.json"],
        docs_url="https://github.com/wellmanifest/authority-lifecycle",
    ),
    "wellmanifest/llm": StandardPack(
        id="wellmanifest/llm",
        name="LLM Policy Boundary",
        owner="wellmanifest/llm",
        description="LLM policy boundary, model profiles, request/response verification, context isolation",
        minimum_level="S3",
        execution_model="protected-conformance",
        owns=["LLM policy boundary"],
        excludes=["runtime provider credentials", "runtime model routing"],
        schemas=["llm-profile.schema.json", "request.schema.json", "response.schema.json"],
        docs_url="https://github.com/wellmanifest/llm",
    ),
    "wellmanifest/logs": StandardPack(
        id="wellmanifest/logs",
        name="Structured Logging Contract",
        owner="wellmanifest/logs",
        description="Structured log contract, diagnostic event vocabulary, JSONL event streams",
        minimum_level="S3",
        execution_model="protected-conformance",
        owns=["structured log contract", "diagnostic event vocabulary"],
        schemas=[],
        docs_url="https://github.com/wellmanifest/logs",
    ),
    "wellmanifest/poa": StandardPack(
        id="wellmanifest/poa",
        name="Plan of Action Contract",
        owner="wellmanifest/poa",
        description="Plan of action execution contracts, step-by-step verifiable action plans",
        minimum_level="S5",
        execution_model="runtime-conformance",
        owns=["plan of action contract"],
        schemas=[],
        docs_url="https://github.com/wellmanifest/poa",
    ),
    "wellmanifest/dsl": StandardPack(
        id="wellmanifest/dsl",
        name="Domain Specific Language Specification",
        owner="wellmanifest/dsl",
        description="DSL interoperability contract, grammar toolchains, fenced syntax definitions",
        minimum_level="S4",
        execution_model="protected-conformance",
        owns=["DSL interoperability contract"],
        schemas=["dsl-manifest.schema.json"],
        docs_url="https://github.com/wellmanifest/dsl",
    ),
    "wellmanifest/code-dsl": StandardPack(
        id="wellmanifest/code-dsl",
        name="Code-Level Semantic Query Contract",
        owner="wellmanifest/code-dsl",
        description="Code-level semantic query contract, AST diagnostics model, code entity extraction",
        minimum_level="S4",
        execution_model="protected-conformance",
        owns=["code-level semantic query contract", "AST diagnostics model"],
        requires=["wellmanifest/dsl"],
        schemas=[],
        docs_url="https://github.com/wellmanifest/code-dsl",
    ),
    "wellmanifest/env-dsl": StandardPack(
        id="wellmanifest/env-dsl",
        name="Environment Contract DSL",
        owner="wellmanifest/env-dsl",
        description="Declarative environment variable contract, secret separation, and deterministic runtime config validation",
        minimum_level="S3",
        execution_model="protected-conformance",
        owns=["environment contract DSL", "secret/env separation"],
        requires=["wellmanifest/dsl"],
        schemas=["env-dsl.schema.json"],
        docs_url="https://github.com/wellmanifest/env-dsl",
    ),
    "wellmanifest/nl-dsl-llm": StandardPack(
        id="wellmanifest/nl-dsl-llm",
        name="Natural Language to DSL via LLM",
        owner="wellmanifest/nl-dsl-llm",
        description="Tripartite natural-language, canonical DSL, and adaptive LLM contract, universal MCP/CLI parity",
        minimum_level="S4",
        execution_model="protected-conformance",
        owns=["tripartite natural-language, canonical DSL, and adaptive LLM contract", "universal MCP/CLI parity"],
        requires=["wellmanifest/dsl", "wellmanifest/llm"],
        schemas=[],
        docs_url="https://github.com/wellmanifest/nl-dsl-llm",
    ),
    "wellmanifest/nl-api-llm": StandardPack(
        id="wellmanifest/nl-api-llm",
        name="Natural Language to Multi-Protocol API via LLM",
        owner="wellmanifest/nl-api-llm",
        description="Tripartite NL-API-LLM architecture, universal API registry, dynamic frontend menu tree, multi-protocol dispatch",
        minimum_level="S4",
        execution_model="protected-conformance",
        owns=[
            "tripartite NL-API-LLM architecture",
            "universal API registry",
            "dynamic frontend menu tree",
            "multi-protocol dispatch",
        ],
        requires=["wellmanifest/dsl", "wellmanifest/llm"],
        schemas=[
            "api-registry.schema.json",
            "menu-tree.schema.json",
            "nl-api-query.schema.json",
            "api-action-result.schema.json",
        ],
        docs_url="https://github.com/wellmanifest/nl-api-llm",
    ),
    "wellmanifest/repair-lifecycle": StandardPack(
        id="wellmanifest/repair-lifecycle",
        name="Repair and Remediation Lifecycle",
        owner="wellmanifest/repair-lifecycle",
        description="Automated repair, remediation intent templates, patch generation and validation",
        minimum_level="S5",
        execution_model="runtime-conformance",
        owns=["repair and remediation lifecycle"],
        requires=["wellmanifest/lifecycle"],
        schemas=["remediation-intent.schema.json"],
        docs_url="https://github.com/wellmanifest/repair-lifecycle",
    ),
    "wellmanifest/deployment": StandardPack(
        id="wellmanifest/deployment",
        name="Deployment Contract",
        owner="wellmanifest/deployment",
        description="Deployment specifications, target topologies, environment manifests, release verification",
        minimum_level="S5",
        execution_model="runtime-conformance",
        owns=["deployment contract", "deployment verification"],
        schemas=[],
        docs_url="https://github.com/wellmanifest/deployment",
    ),
    "wellmanifest/agent": StandardPack(
        id="wellmanifest/agent",
        name="Autonomous Agent Contract",
        owner="wellmanifest/agent",
        description="Autonomous AI Agent contract, participant guidelines, host registry, execution permissions",
        minimum_level="S4",
        execution_model="protected-conformance",
        owns=["agent contract", "agent host governance", "participant guidelines"],
        requires=["wellmanifest/new-project"],
        schemas=["agent.schema.json", "agent-hosts.schema.json"],
        docs_url="https://github.com/wellmanifest/agent",
    ),
    "wellmanifest/docs": StandardPack(
        id="wellmanifest/docs",
        name="Documentation Gate & Readiness",
        owner="wellmanifest/docs",
        description="Documentation readiness validation, policy-as-code documentation requirements, docs gate",
        minimum_level="S3",
        execution_model="protected-conformance",
        owns=["documentation readiness", "docs gate"],
        schemas=["readiness.schema.json"],
        docs_url="https://github.com/wellmanifest/docs",
    ),
    "wellmanifest/report": StandardPack(
        id="wellmanifest/report",
        name="Reproducible Report & Deliverable Receipts",
        owner="wellmanifest/report",
        description="Deterministic report envelopes, evidence digests, and machine-verifiable deliverable receipts",
        minimum_level="S3",
        execution_model="protected-conformance",
        owns=["reproducible report receipts", "report verification"],
        requires=["wellmanifest/docs"],
        schemas=["report.schema.json"],
        docs_url="https://github.com/wellmanifest/report",
    ),
    "wellmanifest/policy-dsl": StandardPack(
        id="wellmanifest/policy-dsl",
        name="Policy DSL",
        owner="wellmanifest/policy-dsl",
        description="Policy-as-code declarative DSL, rule validation and compliance assertions",
        minimum_level="S4",
        execution_model="protected-conformance",
        owns=["policy DSL spec", "policy enforcement"],
        requires=["wellmanifest/dsl"],
        schemas=[],
        docs_url="https://github.com/wellmanifest/policy-dsl",
    ),
    "wellmanifest/skills": StandardPack(
        id="wellmanifest/skills",
        name="Agent Skills Specification",
        owner="wellmanifest/skills",
        description="Agent skill execution models, operation profiles, tool definition interfaces",
        minimum_level="S3",
        execution_model="protected-conformance",
        owns=["skill execution", "tool interfaces"],
        schemas=["skill.schema.json", "skill-execution.schema.json", "skill-operation-profile.schema.json"],
        docs_url="https://github.com/wellmanifest/skills",
    ),
    "wellmanifest/account-runtime": StandardPack(
        id="wellmanifest/account-runtime",
        name="Account Runtime Standard",
        owner="wellmanifest/account-runtime",
        description="Account runtime, service access controls, multi-tenant credential isolation",
        minimum_level="S4",
        execution_model="runtime-conformance",
        owns=["service access", "account runtime"],
        schemas=["account-runtime.schema.json", "service-access.schema.json"],
        docs_url="https://github.com/wellmanifest/account-runtime",
    ),
    "wellmanifest/saas-lifecycle": StandardPack(
        id="wellmanifest/saas-lifecycle",
        name="SaaS Lifecycle Standard",
        owner="wellmanifest/saas-lifecycle",
        description="SaaS integration lifecycle, adapter profiles, subscription and quota boundaries",
        minimum_level="S4",
        execution_model="runtime-conformance",
        owns=["saas adapter profile", "saas lifecycle"],
        requires=["wellmanifest/lifecycle"],
        schemas=["saas-lifecycle.schema.json", "saas-adapter-profile.schema.json"],
        docs_url="https://github.com/wellmanifest/saas-lifecycle",
    ),
    "wellmanifest/twin-lifecycle": StandardPack(
        id="wellmanifest/twin-lifecycle",
        name="Digital Twin Lifecycle",
        owner="wellmanifest/twin-lifecycle",
        description="Digital twin simulation lifecycle, state sync, telemetry verification",
        minimum_level="S4",
        execution_model="runtime-conformance",
        owns=["twin lifecycle"],
        requires=["wellmanifest/lifecycle"],
        schemas=["twin-lifecycle.schema.json"],
        docs_url="https://github.com/wellmanifest/twin-lifecycle",
    ),
    "wellmanifest/anonym": StandardPack(
        id="wellmanifest/anonym",
        name="Data Anonymization Standard",
        owner="wellmanifest/anonym",
        description="PII sanitization, data anonymization envelopes, privacy compliance assertions",
        minimum_level="S3",
        execution_model="protected-conformance",
        owns=["data anonymization", "privacy boundaries"],
        schemas=[],
        docs_url="https://github.com/wellmanifest/anonym",
    ),
    "wellmanifest/legal-lifecycle": StandardPack(
        id="wellmanifest/legal-lifecycle",
        name="Legal & License Lifecycle",
        owner="wellmanifest/legal-lifecycle",
        description="License compliance, contributor agreements, copyright assertions and audits",
        minimum_level="S3",
        execution_model="protected-conformance",
        owns=["license compliance", "contributor agreements"],
        requires=["wellmanifest/lifecycle"],
        schemas=["legal-lifecycle.schema.json"],
        docs_url="https://github.com/wellmanifest/legal-lifecycle",
    ),
    "wellmanifest/product-lifecycle": StandardPack(
        id="wellmanifest/product-lifecycle",
        name="Product Lifecycle Management",
        owner="wellmanifest/product-lifecycle",
        description="Product maturity stages, release gates, deprecation and sunset schedules",
        minimum_level="S3",
        execution_model="protected-conformance",
        owns=["product maturity stages", "release gates"],
        requires=["wellmanifest/lifecycle"],
        schemas=["product-lifecycle.schema.json"],
        docs_url="https://github.com/wellmanifest/product-lifecycle",
    ),
    "wellmanifest/session-recovery": StandardPack(
        id="wellmanifest/session-recovery",
        name="LLM Session Recovery & Storage Resilience",
        owner="wellmanifest/session-recovery",
        description="Normative standard for LLM host session resilience, crash isolation, automated storage salvage, and state rehydration",
        minimum_level="S3",
        execution_model="protected-conformance",
        owns=["LLM session recovery", "conversation storage resilience", "host resumption protocol", "session crash isolation", "state rehydration"],
        schemas=["session-recovery.schema.json"],
        docs_url="https://github.com/wellmanifest/session-recovery",
    ),
    "wellmanifest/lifecycle": StandardPack(
        id="wellmanifest/lifecycle",
        name="Lifecycle State-Machine Meta-Standard",
        owner="wellmanifest/lifecycle",
        description="Deterministic state-machine DSL, compaction desugaring, and graph invariants for domain lifecycles",
        minimum_level="S4",
        execution_model="protected-conformance",
        owns=["lifecycle meta-DSL", "lifecycle graph invariants", "lifecycle compaction audit"],
        schemas=["lifecycle.schema.json"],
        docs_url="https://github.com/wellmanifest/lifecycle",
    ),
    "wellmanifest/mcp": StandardPack(
        id="wellmanifest/mcp",
        name="Model Context Protocol URI Reuse & Operation Contract",
        owner="wellmanifest/mcp",
        description="Deterministic MCP URI operation registry, read/mutate separation, and replayable execution receipts",
        minimum_level="S4",
        execution_model="protected-conformance",
        owns=["MCP operation registry", "MCP URI reuse contract", "MCP task receipt replay"],
        schemas=["mcp-operation-catalog.schema.json", "mcp-task-receipt.schema.json"],
        docs_url="https://github.com/wellmanifest/mcp",
    ),
    "wellmanifest/dockuri": StandardPack(
        id="wellmanifest/dockuri",
        name="DockURI Process Registry & MCP Server Standard",
        owner="wellmanifest/dockuri",
        description="Universal URI process registry (dockuri.json/dockuri.yaml), MCP server adapter, and process execution envelope",
        minimum_level="S3",
        execution_model="protected-conformance",
        owns=["DockURI process registry", "MCP URI process dispatch", "universal process conformation"],
        requires=["wellmanifest/uriprocess", "wellmanifest/mcp"],
        schemas=["dockuri-manifest.schema.json", "dockuri-envelope.schema.json"],
        docs_url="https://github.com/wellmanifest/dockuri",
    ),
    "wellmanifest/hostguard": StandardPack(
        id="wellmanifest/hostguard",
        name="Host Resource & Storage Guard Contract",
        owner="wellmanifest/hostguard",
        description="Deterministic host probe, storage floor resilience, threat classification, and autonomous remediation",
        minimum_level="S4",
        execution_model="protected-conformance",
        owns=["host resource probe", "storage floor resilience", "host remediation receipts"],
        schemas=["hostguard.probe.v1.schema.json"],
        docs_url="https://github.com/wellmanifest/hostguard",
    ),
    "wellmanifest/flowguard": StandardPack(
        id="wellmanifest/flowguard",
        name="Bounded Concurrency & Multi-Task Flow Governor",
        owner="wellmanifest/flowguard",
        description="Adaptive multi-task concurrency governor, Head-of-Line decongestion, DAG isolation and rate-limit backpressure",
        minimum_level="S3",
        execution_model="protected-conformance",
        owns=["adaptive concurrency governance", "DAG flow scheduling", "HoL decongestion quarantine"],
        schemas=["flowguard.policy.v1.schema.json"],
        docs_url="https://github.com/wellmanifest/flowguard",
    ),
    "wellmanifest/status": StandardPack(
        id="wellmanifest/status",
        name="Status Signal & Telemetry Standard",
        owner="wellmanifest/status",
        description="Standardized status signal taxonomy, readiness probes, and live status telemetry envelopes",
        minimum_level="S3",
        execution_model="protected-conformance",
        owns=["status signal taxonomy", "live status telemetry"],
        schemas=["status.schema.json"],
        docs_url="https://github.com/wellmanifest/status",
    ),
    "wellmanifest/performance": StandardPack(
        id="wellmanifest/performance",
        name="Performance Budget & Regression Gate Standard",
        owner="wellmanifest/performance",
        description="Declarative performance budgets, latency/throughput envelopes, and benchmark regression gates",
        minimum_level="S3",
        execution_model="protected-conformance",
        owns=["performance budget contracts", "benchmark regression gates"],
        schemas=["performance-budget.schema.json"],
        docs_url="https://github.com/wellmanifest/performance",
    ),
}

# Standard profiles grouping multiple standard packs
PROFILES_CATALOG: Dict[str, Profile] = {
    "baseline": Profile(
        name="baseline",
        description="Mandatory baseline governance required for all standard projects",
        extends=[],
        requirements=[
            {"id": "wellmanifest/new-project", "minimumLevel": "S4"},
            {"id": "wellmanifest/git-lifecycle", "minimumLevel": "S4"},
            {"id": "wellmanifest/worktrees", "minimumLevel": "S3"},
            {"id": "wellmanifest/merge", "minimumLevel": "S4"},
            {"id": "wellmanifest/validation-attestation", "minimumLevel": "S4"},
            {"id": "wellmanifest/ticket-lifecycle", "minimumLevel": "S3"},
            {"id": "wellmanifest/logs", "minimumLevel": "S3"},
            {"id": "wellmanifest/docs", "minimumLevel": "S3"},
        ],
    ),
    "domain-pack": Profile(
        name="domain-pack",
        description="Baseline + DSL and grammar specifications",
        extends=["baseline"],
        requirements=[
            {"id": "wellmanifest/dsl", "minimumLevel": "S4"},
            {"id": "wellmanifest/code-dsl", "minimumLevel": "S4"},
        ],
    ),
    "runtime-service": Profile(
        name="runtime-service",
        description="Baseline + effectful runtime authority, POA, and logging",
        extends=["baseline"],
        requirements=[
            {"id": "wellmanifest/poa", "minimumLevel": "S5"},
            {"id": "wellmanifest/authority-lifecycle", "minimumLevel": "S5"},
            {"id": "wellmanifest/logs", "minimumLevel": "S5"},
        ],
    ),
    "agent-executor": Profile(
        name="agent-executor",
        description="Runtime service + autonomous agent governance, repair, and skills",
        extends=["runtime-service"],
        requirements=[
            {"id": "wellmanifest/agent", "minimumLevel": "S4"},
            {"id": "wellmanifest/repair-lifecycle", "minimumLevel": "S5"},
            {"id": "wellmanifest/validation-attestation", "minimumLevel": "S5"},
            {"id": "wellmanifest/skills", "minimumLevel": "S4"},
            {"id": "wellmanifest/llm", "minimumLevel": "S4"},
            {"id": "wellmanifest/session-recovery", "minimumLevel": "S3"},
        ],
    ),
    "deployment": Profile(
        name="deployment",
        description="Runtime service + deployment and release verification",
        extends=["runtime-service"],
        requirements=[
            {"id": "wellmanifest/deployment", "minimumLevel": "S5"},
            {"id": "wellmanifest/merge", "minimumLevel": "S5"},
        ],
    ),
    "embedded-fleet": Profile(
        name="embedded-fleet",
        description="Deployment + embedded semantic versioning and heterogeneous fleet release",
        extends=["deployment"],
        requirements=[
            {"id": "wellmanifest/semver", "minimumLevel": "S3"},
        ],
    ),
    "full": Profile(
        name="full",
        description="Comprehensive profile including all Wellmanifest standards",
        extends=["baseline", "domain-pack", "agent-executor", "deployment"],
        requirements=[{"id": k, "minimumLevel": v.minimum_level} for k, v in STANDARDS_CATALOG.items()],
    ),
}


def get_standard(standard_id: str) -> Optional[StandardPack]:
    """Retrieve standard pack by id or alias."""
    aliases = {
        "wellmanifest/git": "wellmanifest/git-lifecycle",
        "git": "wellmanifest/git-lifecycle",
        "git-lifecycle": "wellmanifest/git-lifecycle",
        "new-project": "wellmanifest/new-project",
        "worktrees": "wellmanifest/worktrees",
        "ticket": "wellmanifest/ticket-lifecycle",
        "ticket-lifecycle": "wellmanifest/ticket-lifecycle",
        "agent": "wellmanifest/agent",
        "merge": "wellmanifest/merge",
        "validation-attestation": "wellmanifest/validation-attestation",
        "dsl": "wellmanifest/dsl",
        "code-dsl": "wellmanifest/code-dsl",
        "env-dsl": "wellmanifest/env-dsl",
        "nl-dsl": "wellmanifest/nl-dsl-llm",
        "nl-dsl-llm": "wellmanifest/nl-dsl-llm",
        "nl-api": "wellmanifest/nl-api-llm",
        "nl-api-llm": "wellmanifest/nl-api-llm",
        "nohardcode": "wellmanifest/nohardcode",
        "taskand": "wellmanifest/taskand",
        "data-plane": "wellmanifest/data-plane",
        "uriprocess": "wellmanifest/uriprocess",
        "ssot": "wellmanifest/ssot",
        "project-ssot": "wellmanifest/project-ssot",
        "semver": "wellmanifest/semver",
        "nl-uri-dsl-llm": "wellmanifest/nl-uri-dsl-llm",
        "reuse": "wellmanifest/reuse",
        "modularity": "wellmanifest/modularity",
        "priority": "wellmanifest/priority",
        "lifecycle": "wellmanifest/lifecycle",
        "policy-dsl": "wellmanifest/policy-dsl",
        "mcp": "wellmanifest/mcp",
        "dockuri": "wellmanifest/dockuri",
        "hostguard": "wellmanifest/hostguard",
        "flowguard": "wellmanifest/flowguard",
        "docs": "wellmanifest/docs",
        "logs": "wellmanifest/logs",
        "llm": "wellmanifest/llm",
        "poa": "wellmanifest/poa",
        "report": "wellmanifest/report",
        "session-recovery": "wellmanifest/session-recovery",
        "status": "wellmanifest/status",
        "performance": "wellmanifest/performance",
    }
    normalized = aliases.get(standard_id, standard_id)
    return STANDARDS_CATALOG.get(normalized)


def expand_standard_dependencies(standard_ids: Iterable[str]) -> Dict[str, str]:
    """Expand transitive `requires` dependencies for a set of standard IDs.

    Raises ValueError on unknown standards or dependency cycles.
    Returns a dictionary mapping canonical standard ID -> minimum conformance level.
    """
    resolved: Dict[str, str] = {}
    done: set[str] = set()
    active: set[str] = set()

    def visit(raw_id: str) -> None:
        pack = get_standard(raw_id)
        if pack is None:
            raise ValueError(f"Unknown standard: {raw_id}")
        cid = pack.id
        if cid in active:
            raise ValueError(f"Standard dependency cycle detected at: {cid}")
        if cid in done:
            return
        active.add(cid)
        for dep_id in pack.requires:
            visit(dep_id)
        active.remove(cid)
        done.add(cid)
        resolved[cid] = max(resolved.get(cid, "S0"), pack.minimum_level)

    for raw_id in standard_ids:
        visit(raw_id)
    return resolved


def missing_standard_dependencies(
    registered_ids: Iterable[str],
    *,
    include_baseline_meta: bool = False,
) -> Dict[str, List[str]]:
    """Return missing direct `requires` dependencies for a set of registered standards.

    By default (`include_baseline_meta=False`), `wellmanifest/lifecycle` is only
    required for `git-lifecycle` / `ticket-lifecycle` when non-baseline lifecycle
    or domain standards are also registered, preserving compatibility with minimal
    baseline-only projections.
    """
    canonical_set: set[str] = set()
    packs: List[StandardPack] = []
    for raw_id in registered_ids:
        pack = get_standard(raw_id)
        if pack is not None:
            canonical_set.add(pack.id)
            packs.append(pack)
        else:
            canonical_set.add(raw_id)

    baseline_ids = {item["id"] for item in PROFILES_CATALOG["baseline"].requirements}
    has_non_baseline = bool(canonical_set - baseline_ids)

    missing: Dict[str, List[str]] = {}
    for pack in packs:
        absent: List[str] = []
        for dep_id in pack.requires:
            if (
                not include_baseline_meta
                and not has_non_baseline
                and pack.id in ("wellmanifest/git-lifecycle", "wellmanifest/ticket-lifecycle")
                and dep_id == "wellmanifest/lifecycle"
            ):
                continue
            if dep_id not in canonical_set:
                absent.append(dep_id)
        if absent:
            missing[pack.id] = sorted(absent)
    return missing


def list_standards() -> List[StandardPack]:
    """List all registered standards."""
    return list(STANDARDS_CATALOG.values())


def get_profile(name: str) -> Optional[Profile]:
    """Retrieve profile by name."""
    return PROFILES_CATALOG.get(name)


def list_profiles() -> List[Profile]:
    """List all registered profiles."""
    return list(PROFILES_CATALOG.values())
