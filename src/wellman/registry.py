"""Wellmanifest Standards Registry and Profile Catalog.

Unified single-source-of-truth definition for all Wellmanifest standards,
execution models, conformance levels (S0-S5), and adoption profiles.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


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
        schemas=[],
        docs_url="https://github.com/wellmanifest/code-dsl",
    ),
    "wellmanifest/nl-dsl-llm": StandardPack(
        id="wellmanifest/nl-dsl-llm",
        name="Natural Language to DSL via LLM",
        owner="wellmanifest/nl-dsl-llm",
        description="Tripartite natural-language, canonical DSL, and adaptive LLM contract, universal MCP/CLI parity",
        minimum_level="S4",
        execution_model="protected-conformance",
        owns=["tripartite natural-language, canonical DSL, and adaptive LLM contract", "universal MCP/CLI parity"],
        schemas=[],
        docs_url="https://github.com/wellmanifest/nl-dsl-llm",
    ),
    "wellmanifest/repair-lifecycle": StandardPack(
        id="wellmanifest/repair-lifecycle",
        name="Repair and Remediation Lifecycle",
        owner="wellmanifest/repair-lifecycle",
        description="Automated repair, remediation intent templates, patch generation and validation",
        minimum_level="S5",
        execution_model="runtime-conformance",
        owns=["repair and remediation lifecycle"],
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
    "wellmanifest/policy-dsl": StandardPack(
        id="wellmanifest/policy-dsl",
        name="Policy DSL",
        owner="wellmanifest/policy-dsl",
        description="Policy-as-code declarative DSL, rule validation and compliance assertions",
        minimum_level="S4",
        execution_model="protected-conformance",
        owns=["policy DSL spec", "policy enforcement"],
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
        schemas=["product-lifecycle.schema.json"],
        docs_url="https://github.com/wellmanifest/product-lifecycle",
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
    "full": Profile(
        name="full",
        description="Comprehensive profile including all Wellmanifest standards",
        extends=["baseline", "domain-pack", "agent-executor", "deployment"],
        requirements=[{"id": k, "minimumLevel": v.minimum_level} for k, v in STANDARDS_CATALOG.items()],
    ),
}


def get_standard(standard_id: str) -> Optional[StandardPack]:
    """Retrieve standard pack by id or alias."""
    # Normalize aliases
    aliases = {
        "wellmanifest/git": "wellmanifest/git-lifecycle",
        "git": "wellmanifest/git-lifecycle",
        "new-project": "wellmanifest/new-project",
        "worktrees": "wellmanifest/worktrees",
        "ticket": "wellmanifest/ticket-lifecycle",
        "agent": "wellmanifest/agent",
        "merge": "wellmanifest/merge",
        "dsl": "wellmanifest/dsl",
    }
    normalized = aliases.get(standard_id, standard_id)
    return STANDARDS_CATALOG.get(normalized)


def list_standards() -> List[StandardPack]:
    """List all registered standards."""
    return list(STANDARDS_CATALOG.values())


def get_profile(name: str) -> Optional[Profile]:
    """Retrieve profile by name."""
    return PROFILES_CATALOG.get(name)


def list_profiles() -> List[Profile]:
    """List all registered profiles."""
    return list(PROFILES_CATALOG.values())
