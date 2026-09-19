# wellman


## AI Cost Tracking

![PyPI](https://img.shields.io/badge/pypi-costs-blue) ![Version](https://img.shields.io/badge/version-0.20.36-blue) ![Python](https://img.shields.io/badge/python-3.9+-blue) ![License](https://img.shields.io/badge/license-Apache--2.0-green)
![AI Cost](https://img.shields.io/badge/AI%20Cost-$0.66-orange) ![Human Time](https://img.shields.io/badge/Human%20Time-1.0h-blue) ![Model](https://img.shields.io/badge/Model-openrouter%2Fqwen%2Fqwen3--coder--next-lightgrey)

- 🤖 **LLM usage:** $0.6582 (4 commits)
- 👤 **Human dev:** ~$100 (1.0h @ $100/h, 30min dedup)

Generated on 2026-09-19 using [openrouter/qwen/qwen3-coder-next](https://openrouter.ai/qwen/qwen3-coder-next)

---

**Wellman** is the unified runtime, standards catalog, and policy-as-code validator for all **Wellmanifest** standards.

Instead of copying hundreds of kilobytes of vendored checker scripts into every repository, `wellman` provides a standardized, dependency-free CLI and programmatic engine that enforces Wellmanifest standards across your organization.

---

## Supported Standards

`wellman` supports the complete suite of Wellmanifest standards:

| Standard ID | Name | Level | Model |
|-------------|------|-------|-------|
| `wellmanifest/new-project` | Repository Bootstrap & Pack Composition | S4 | Protected |
| `wellmanifest/git-lifecycle` | Branch, Ref, and PR Lifecycle | S4 | Protected |
| `wellmanifest/worktrees` | Canonical Worktree Layout & Overlap Guard | S3 | Protected |
| `wellmanifest/ticket-lifecycle` | Ticket Semantics, Leases & Activity | S3 | Protected |
| `wellmanifest/merge` | Autonomous Merge Standard | S4 | Protected |
| `wellmanifest/validation-attestation` | Exact-Head Evidence & Attestation | S4 | Protected |
| `wellmanifest/authority-lifecycle` | Authority Lease & Expiry Semantics | S5 | Runtime |
| `wellmanifest/agent` | Autonomous AI Agent Contract & Host Registry | S4 | Protected |
| `wellmanifest/docs` | Documentation Readiness & Docs Gate | S3 | Protected |
| `wellmanifest/dsl` | Domain Specific Language Interoperability | S4 | Protected |
| `wellmanifest/code-dsl` | Code-Level AST Semantic Query Contract | S4 | Protected |
| `wellmanifest/nl-dsl-llm` | Tripartite NL, Canonical DSL & LLM Contract | S4 | Protected |
| `wellmanifest/repair-lifecycle` | Automated Repair & Remediation Lifecycle | S5 | Runtime |
| `wellmanifest/deployment` | Deployment Specifications & Topologies | S5 | Runtime |
| `wellmanifest/llm` | LLM Policy Boundary & Profile Envelopes | S3 | Protected |
| `wellmanifest/logs` | Structured Log Contract & Diagnostic Events | S3 | Protected |
| `wellmanifest/poa` | Plan of Action Execution Contracts | S5 | Runtime |
| `wellmanifest/skills` | Agent Skill Execution & Tool Interfaces | S3 | Protected |
| `wellmanifest/account-runtime` | Multi-Tenant Account & Service Access | S4 | Runtime |
| `wellmanifest/saas-lifecycle` | SaaS Adapter Profiles & Subscriptions | S4 | Runtime |
| `wellmanifest/twin-lifecycle` | Digital Twin Lifecycle & Telemetry | S4 | Runtime |
| `wellmanifest/anonym` | PII Sanitization & Data Anonymization | S3 | Protected |
| `wellmanifest/legal-lifecycle` | License Compliance & Contributor Agreements | S3 | Protected |
| `wellmanifest/product-lifecycle`| Product Maturity Stages & Release Gates | S3 | Protected |

---

## Quick Start

### Installation

```bash
pip install wellman
# or using uv
uv add --group governance wellman
```

Zero external dependencies required. Works on Python 3.9+.

---

## CLI Usage

### 1. List all supported standards

```bash
wellman standards
# or JSON format
wellman standards --json
```

### 2. Inspect a standard specification

```bash
wellman info wellmanifest/git-lifecycle
```

### 3. Check standards compliance in a repository

```bash
wellman check
# or specify repository root
wellman check --root /path/to/repo
# or output machine-readable JSON
wellman check --json
```

### 4. Adopt a standard or profile into a repository

```bash
# Default: register baseline and inferred capability requirements, additively.
wellman adopt --root /path/to/project
# Preview without changing any files; optional explicit capability profile.
wellman adopt auto --profile agent-executor --dry-run --json

wellman adopt wellmanifest/git-lifecycle
# or adopt a profile
wellman adopt baseline
# Explicit bootstrap for an existing directory which is not yet in Git.
wellman adopt auto --root /path/to/new-project --bootstrap
```

Automatic registration writes `.governance/standard-requirements.json`, not an
adoption certificate. It works for any language, mixed-language repositories,
documentation-only projects and unknown project types. Every project gets the
baseline; declared profiles/roles, Docker/Compose files and domain operation
catalogs add capability profiles. Profile inheritance is transitive and the
strongest required level wins. `--profile` can supply capabilities that cannot
be inferred from these signals.

The CLI discovers the Git root from the current directory or `--root` argument.
A nested directory writes to its repository root; a linked worktree writes to
that worktree, not the primary checkout. Inherited Git location overrides are
ignored. Symlinks in the requested path or adoption destinations are rejected
before writes. Outside Git, use `--bootstrap` explicitly; bare or broken Git
repositories still fail. The Python `register(root)` API accepts an explicit
directory without Git discovery, while rejecting symlink paths.

These files belong to the repository's `.governance/` directory, not a global
`~/.local` directory. Final reports belong in the owning repository's `docs/`
under its adopted Docs contract. Existing external controller, credential and
protected validation stores are separate authority infrastructure and are not
moved by adoption.

Repeated registration is idempotent and additive: existing requirements,
custom metadata, adoption manifests, pinned revisions and evidence are preserved.
Invalid inputs and concurrent writers fail explicitly. Explicit standard/profile
adoption also registers the baseline and selected requirements. Existing explicit
adoption still requires `--force` to replace a scaffold; auto mode never replaces
it. The command does not scan or modify other repositories, install background
watchers, fetch packages, grant leases, change protected CI or claim S3–S5
conformance. `minimumLevel` is a requirement, not an observed compliance level.

### 5. Validate a JSON/YAML file against bundled schemas

```bash
wellman validate .governance/manifest.json
wellman validate project/ticket-001/intent.json --schema intent
```

### 6. Run deterministic governance gate (CI / Pre-commit)

For an adopted repository, use its pinned managed gate:

```bash
./project/governance-check.sh
```

`wellman gate` currently uses the package-bundled checker; it does not select a
repository's pinned checker automatically. `wellman check` covers only the
implemented subset of the catalog. In particular, the catalog's Docs entry is
not yet an executable Docs checker in this release. Preserve the repository's
adopted Docs adapter and required CI checks; registration is not a replacement
for either.

---

## Profiles

Wellman supports composite governance profiles:

- **`baseline`**: `new-project` (S4), `git-lifecycle` (S4), `worktrees` (S3), `merge` (S4), `validation-attestation` (S4), `ticket-lifecycle` (S3), `logs` (S3).
- **`domain-pack`**: `baseline` + `dsl` (S4), `code-dsl` (S4).
- **`runtime-service`**: `baseline` + `poa` (S5), `authority-lifecycle` (S5), `logs` (S5).
- **`agent-executor`**: `runtime-service` + `agent` (S4), `repair-lifecycle` (S5), `validation-attestation` (S5), `skills` (S4), `llm` (S4).
- **`deployment`**: `runtime-service` + `deployment` (S5), `merge` (S5).
- **`full`**: All Wellmanifest standards.

View all profiles:
```bash
wellman profiles
```

---

## Python API

```python
from wellman import (
    list_standards,
    get_standard,
    StandardsValidator,
    ConformanceRunner,
)

# Inspect standard
git_std = get_standard("wellmanifest/git-lifecycle")
print(git_std.name, git_std.minimum_level)

# Run conformance check programmatically
runner = ConformanceRunner(root=Path("."))
findings = runner.run_all()
for finding in findings:
    print(finding.code, finding.severity, finding.message)
```

---

## License

Licensed under Apache-2.0.
