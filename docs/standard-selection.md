# Structure-aware standard selection

`wellman recommend` augments existing additive adoption. The default is read-only:

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
