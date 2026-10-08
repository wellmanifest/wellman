# Structure-aware standard selection

`wellman recommend` supports structure-based recommendations and evidence-bound
selection plans. Both default to read-only proposals. The evidence workflow below
adds current-adoption comparison and explicit human backlog export; the legacy
commands retain their existing additive registration boundary.

## Structure based recommendations

The default is read-only:

```sh
wellman recommend --root /path/to/project --analyze --json
wellman recommend --root /path/to/project --ast /path/to/analysis.json --json
wellman recommend --root /path/to/project --analyze --llm \
  --hint 'This library will expose an LLM API' --timeout 30 --json
```

Code2LLM must already be installed for `--analyze`. Wellman invokes it with JSON
output in a temporary directory and no persistent cache. Analysis is static;
source is never imported. Existing `analysis.json` inputs must identify the
same checkout or a source directory within it. Reports are bounded to 20 MiB.
When Code2LLM omits imports, Wellman parses only its reported Python source
modules with the standard-library AST, retaining source digests and coverage
gaps. Other languages need imports supplied by Code2LLM. Tests, examples,
bundled checkers and generated/config modules do not imply runtime capability.
Import evidence is a recommendation heuristic, not proof that a service runs.

Every project retains baseline and previously registered requirements. CLI
imports alone do not add a runtime profile. Source web-framework imports
recommend `runtime-service`; LLM client imports recommend `wellmanifest/llm`;
AST/CST analysis imports recommend `wellmanifest/code-dsl`. Existing declared
profiles, stack/deployment contracts and operation catalogs are also preserved
through the existing adoption API, so stronger declared requirements may remain
even if the graph contains no matching imports.

## Supporting evidence

```sh
wellman recommend --root /path/to/project --ast /path/to/analysis.json \
  --evidence regix=/path/to/regression.json \
  --evidence redup=/path/to/duplicates.json --json
```

The report lists availability and roles for `regix`, `prefact`, `glon`, `goal`,
`code2logic`, `code2llm`, `redup`, `doql`, `sumd` and `code2docs`. Supporting JSON
reports are hashed as evidence; Wellman does not execute these tools or treat
their contents as policy. Imported reports have unverified freshness. A digest
binds bytes, not authenticity, full source coverage or conformance.

## SubLLM boundary

`--llm` uses the optional installed `subllm.complete` API with application
`wellman`, function `standard-selection` and the caller's bounded timeout.
Provider selection, credentials and failover belong to SubLLM policy. Only the
normalized structure, catalog, deterministic selection and explicit hints are
sent; raw source and supporting report contents are not transmitted. Provider
errors preserve deterministic results and expose only the exception type.
Missing SubLLM is reported as unavailable; no dependency is auto-installed.

Known standard IDs and reasons become advisory suggestions. Unknown catalog IDs
are rejected. Valid new `wellmanifest/<slug>` IDs become proposals requiring a
separate standard-owner ticket, contract, implementation and independent review.
An LLM cannot add standards to the catalog, alter required CI checks, grant
conformance or execute an update.

## Register and update

```sh
# Explicitly add only the deterministic catalog requirements to this checkout.
wellman recommend --root /path/to/project --analyze --register --json

# Existing fleet commands plan adoption effects before applying them.
wellman fleet plan --help
wellman fleet apply --help
```

`--register` reuses the additive lock/CAS registration boundary. It preserves
existing metadata and stronger levels, and never registers LLM suggestions or
new standard proposals. It does not update immutable adoption locks, package
versions or checker pins. Version updates still require the pinned adopter and
protected delivery for each affected repository. A fleet-wide controller,
scheduled source refresh and automatic creation of new standard projects are
not implemented by this command. Use the recommendation report as input to the
existing reviewed fleet planning workflow; do not call registration on a dirty
primary checkout or a project owned by another writer.

## Select different requirements across a fleet

```sh
wellman recommend --root /home/user/projects --fleet --analyze --plan --json
# Explicitly request advisory model analysis, bounded per repository.
wellman recommend --root /home/user/projects --fleet --analyze --llm \
  --timeout 30 --max-projects 20 --plan --json
```

Fleet discovery reuses Wellman's existing contextual Git discovery. Each project
gets its own AST, requirements and optional existing fleet adoption plans.
The default limit is 20 projects (explicit maximum 100); oversized inventories
fail before analysis instead of silently truncating. Analysis/provider deadlines
are per project. Failures are reported per project with a nonzero exit code.
Fleet mode cannot register or reuse one project's imported graph for other
projects. Apply each reviewed plan through existing `fleet apply`, after owning
the target ticket/worktree and revalidating its current state. Earlier writes can
make later plans stale; rebuild them rather than bypassing that check.

Fresh analysis uses the public Code2LLM Python API in a timeout-bounded
subprocess. Install optional `code2llm` in the Python environment running
Wellman, or provide an existing report with `--ast`. The worker disables caches
and parallel workers and exports only module filenames, source kinds and
imports. Full control-flow graphs are not serialized: large projects can fit
within the unchanged 20 MiB module-evidence limit. Imported reports and
supporting evidence retain that same input limit. The analyzed project's code
is parsed, never imported or executed.

## Evidence based selection plans

`recommend --selection-plan` recognizes components, inspects current adoption,
resolves applicability and produces a declarative review plan. Every result has
`mode: recommendation`, `grants_authority: false` and `executable: false`.
`add`, `update`, `repair` and `propose_replace` describe proposed work. `keep`
preserves the current adoption; its conformance can still be unverified.
`defer` identifies missing evidence, metadata, scope, migration or compatibility.

This mode uses three closed contracts: `wellman.observation/v1`,
`wellman.applicability-catalog/v1` and `wellman.selection-plan/v1`. It rejects
legacy analysis, `--register`, `--fleet`, `--plan`, `--llm`, `--ast`, `--evidence`
and `--hint` before effects. Existing recommendation commands above retain their
`wellman.standard-selection/v1` output and behavior.

### Prepare an explicit catalog

Catalog targets must be full immutable commit revisions for known
`wellmanifest/*` IDs. The caller supplies the catalog revision, source, managed
file projections, validators, dependencies, conflicts and migration metadata.
The resolver does not fetch standards or invent target revisions. Missing
metadata produces deferred decisions rather than permission to install.

Generate a catalog outside the observed repository using reviewed inputs:

```python
import json
import os
from pathlib import Path

from wellman.applicability import build_catalog

state = Path(os.environ["SELECTION_STATE"])
catalog = build_catalog(
    json.loads((state / "pins.json").read_text()),
    revision=os.environ["CATALOG_REVISION"],
    trusted_source=os.environ["CATALOG_SOURCE"],
    metadata=json.loads((state / "metadata.json").read_text()),
)
(state / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n")
```

`pins.json` maps standard IDs to exact revisions. `metadata.json` maps those IDs
to catalog fields; it must include the actual managed files and validation
requirements for ready proposals. Source labels and hashes bind input identity;
they are not signatures, external review or conformance attestations.

### Plan from current source or a saved snapshot

```sh
# Capture Git inventory and adoption without running external analyzers.
wellman recommend --root /path/to/repository --selection-plan \
  --catalog /outside/source/catalog.json --json

# Recheck all saved artifact bytes and the live Git/index/adoption state.
wellman recommend --root /path/to/repository --selection-plan \
  --catalog /outside/source/catalog.json \
  --observation /outside/source/snapshot/observation.json --json

# Request explicit classification or exclusion policy.
wellman recommend --root /path/to/repository --selection-plan \
  --catalog /outside/source/catalog.json \
  --scope-policy /outside/source/policy.json --json
```

A policy object accepts only `classification` and `exclusions`. Classification
maps one of `first_party`, `generated`, `vendored`, `runtime_artifact`,
`historical_copy` or `unknown` to a list of relative glob patterns. For example,
`{"classification":{"runtime_artifact":["bench-results/**"]},"exclusions":[]}`
keeps benchmark results outside product capability inference. Saved snapshots
with nondefault classification require that same explicit `--scope-policy`.
Default classification allows recovery of caller exclusions only when the
recorded policy digest matches. Each invocation observes one Git repository.

Git identity and package/workspace manifests confirm component boundaries.
Names such as `executor`, `desktop`, `work` or `vendor` are hints, not capability
proofs. TOML manifests require Python 3.11 or later for the stdlib parser;
older interpreters report an unsupported manifest rather than guessing. The
Python analyzer pipeline below is narrower than multi-language inventory.
Imports, directory names, `pure` labels and benchmark metrics do not establish
agent actions, subscriptions or absence of side effects.

The API `capture_repository` returns observation, inventory and adoption data.
`compose_selection_plan` resolves the same data deterministically.
`assert_plan_current` and `assert_repository_current` reject changed inputs,
live source/index/adoption or artifact bytes with `PLAN_STALE`. The plan hash
binds the observation, catalog, rule version, source scope, adoption, target
revisions and decisions; only its own hash and rendering/output metadata are
excluded. A new observation includes new timestamps and may have a new hash.

### Prepare tools separately and publish analyzer snapshots

Install Wellman separately in the runtime interpreter. The analyzer interpreter
must provide the pinned versions below; preparation is an explicit operation.

| Distribution | Version | Preflight purpose |
| --- | --- | --- |
| code2llm | 0.5.181 | Structure and graph evidence |
| redup | 0.4.48 | Fragment duplication metrics |
| prefact | 0.1.69 | Static diagnostic evidence |
| sumd | 0.3.60 | Verify the `sumr` entry point |

```sh
# Explicit installation/update in a dedicated environment only.
python -m wellman.analysis_environment update --environment /outside/source/tools

# Read-only distribution and sumr metadata/executable checks.
python -m wellman.analysis_environment preflight \
  --python /outside/source/tools/bin/python

# Run fixed commands against separate copies of the same first-party Python files.
python -m wellman.analyzer_snapshot /path/to/repository \
  --output /outside/source/reports --python /outside/source/tools/bin/python
```

The update command uses an environment lock and exact top-level pins, then
verifies the isolated environment, persists the complete package-version lock
and writes its success stamp. A failed install or postflight leaves the prior
success stamp unchanged; it can leave a partially updated environment. A pin
unavailable from the configured package index fails explicitly. Separately
prepared immutable source archives can be used under the caller's tool supply
policy, with source revisions and archive hashes recorded. Preflight never
installs packages. Scanning never calls the update command.

`analyzer_snapshot` parses product source without importing it and copies no
product configuration, package scripts, credentials or hooks into analyzer
inputs. It verifies exact tool versions and environment/source digests before
and after the run. The fixed shared policy excludes root and nested worktrees,
virtual environments, vendored/generated code, benchmark results and
`src/gen/schemas/`; effective paths and the Python-only scope remain in receipts.
Code2llm, redup and prefact run separately with bounded subprocesses. Their
internal normalized output schemas are versioned adapter contracts.

The store must be outside the source repository. Complete validated batches
are retained under `snapshots/`; `current.json` atomically identifies the
snapshot and manifest digest. Failed, unsupported or partial batches retain
diagnostic artifacts without replacing the previous complete pointer. Use the
pointed snapshot's `observation.json` with the saved-observation command above.
A complete tool run does not prove every product capability or conformance.

`missing`, `failed`, `partial`, `unsupported` and `complete` are stage outcomes.
`present`, `absent` and `unknown` describe features. Negative evidence requires
complete matching coverage. A partial graph needs a declared scope;
cross-language edges require source-bound bridge evidence. Class/symbol groups
from code2llm and fragment groups from redup retain separate metric definitions.
Legacy reports without source/provenance receipts remain diagnostic.

### Export proposals to a human backlog

```sh
wellman recommend --root /path/to/repository --selection-plan \
  --catalog /outside/source/catalog.json \
  --export-planfile /outside/source/review-project --json
```

Export is opt-in and requires the native Planfile adapter version `0.1.126`.
The target project must be outside the observed source. Its JSON result is a
`wellman.selection-export/v1` envelope containing the closed plan and a separate
export receipt. Without export, output remains the closed selection plan.

The adapter revalidates source/input identity after acquiring the native store
lock, allocates native IDs and updates only its open, pending, unassigned human
proposals through revision checks. The dedupe key binds repository, component,
standard, scope and target revision. It preserves terminal records, missing
metadata, leases, assigned actors, foreign producers and existing execution
ownership. Dependencies reference actual native ticket IDs. `keep` creates no
new task; deferred decisions can create clarification tasks. Tasks have no
execution script or inputs. Export starts no runner, source write lease, GitHub
synchronization, registration or adoption.

### Workspace adapter and acceptance

The portable [project2.sh example](examples/project2.sh) delegates `preflight`,
`update-tools`, `scan REPOSITORY` and `plan REPOSITORY --catalog FILE` to the
modules above. Run it with Bash from the workspace. `WELLMAN_PYTHON` chooses the
Wellman runtime, `ANALYSIS_ENV` and `ANALYSIS_PYTHON` choose dedicated tools, and
`ANALYSIS_STORE` chooses the separate snapshot store. Calling it without a mode
prints help. It preserves the existing `access-codes` shortcut when the workspace
provides that backend helper. No implicit tool update or README/DSL generation
occurs.

| Acceptance property | Maintained regression evidence |
| --- | --- |
| AC01 Stage outcomes and negative evidence | `test_selection_contracts.py`, `test_evidence.py`, `test_applicability.py` |
| AC02 Source/index changes invalidate evidence | `test_components.py`, `test_analyzer_snapshot.py`, `test_selection_plan.py` |
| AC03 Package and Rust workspace boundaries | `test_components.py` |
| AC04 Explicit file classes and nonproduct evidence | `test_components.py`, `test_evidence.py`, `test_selection_e2e.py` |
| AC05 Partial graphs and cross-language bridge checks | `test_evidence.py` |
| AC06 Pins, drift, exceptions and unverified conformance | `test_adoption_inspection.py` |
| AC07 Keep/add/defer, dependencies and conflicts | `test_applicability.py`, `test_selection_e2e.py` |
| AC08 Advisory data cannot execute effects | `test_selection_contracts.py`, `test_cli.py`, `test_applicability.py` |
| AC09 Determinism and stale or tampered plans | `test_selection_plan.py`, `test_selection_e2e.py` |
| AC10 Atomic snapshots and separate tool updates | `test_analyzer_snapshot.py`, `test_analysis_environment.py` |
| AC11 Idempotent backlog, CAS and ownership preservation | `test_fleet.py` |
| AC12 Library/executor/desktop/benchmark acceptance without source changes | `test_selection_e2e.py` |

This first stage produces evidence and review proposals. Preparing patches,
three-way standard migration, validation attestations and controlled adoption
are subsequent governed work; the current commands issue no deployment approval.

A real analyzer acceptance run on a small Python fixture completed all three
pinned stages and published a complete snapshot. Saved-observation planning
and explicit backlog export preserved the source; a subsequent run with the
older workspace analyzer versions retained diagnostics and left the complete
pointer unchanged. This demonstrates the bounded Python path, not coverage of
the entire multi-repository workspace. Catalog pins in that fixture were
synthetic and granted no adoption authority.
