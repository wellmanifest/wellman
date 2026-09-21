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
wellman adopt wellmanifest/git-lifecycle
# or adopt a profile
wellman adopt baseline
# Adoption binds repository-local metadata to `origin`.
# For a repository without a remote, pass `--repository owner/name`.
wellman adopt baseline --repository acme/example

### 5. Operate on a local repository fleet

```bash
# read-only inventory
wellman fleet discover --root /workspace/wellmanifest

# read-only plan; dirty repositories are blocked by default
wellman fleet plan baseline --root /workspace/wellmanifest --json

# apply only after reviewing the plan
wellman fleet adopt baseline --root /workspace/wellmanifest --apply

# update only wellman-owned manifest version fields as part of the rollout
wellman fleet adopt baseline --root /workspace/wellmanifest \
  --update-manifests --apply

# audit every discovered repository
wellman fleet check --root /workspace/wellmanifest --json
```

Fleet adoption does not overwrite dirty repositories unless `--allow-dirty` is
explicitly supplied. Existing manifests are merged only in wellman-owned
version fields; repository-specific configuration is preserved.
```

### 5. Validate a JSON/YAML file against bundled schemas

```bash
wellman validate .governance/manifest.json
wellman validate project/ticket-001/intent.json --schema intent
```

### 6. Run deterministic governance gate (CI / Pre-commit)

```bash
wellman gate --preflight
```

---

## Profiles

Wellman supports composite governance profiles:

- **`baseline`**: `new-project` (S4), `git-lifecycle` (S4), `worktrees` (S3), `merge` (S4), `validation-attestation` (S4), `ticket-lifecycle` (S3), `logs` (S3), `docs` (S3).
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
