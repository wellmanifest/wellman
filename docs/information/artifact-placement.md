---
{
  "schema": "wellmanifest.docs/document/v1",
  "id": "artifact-placement",
  "kind": "information",
  "version": 1,
  "title": "Project-owned document delivery through Wellman",
  "status": "proposed",
  "owner": "wellmanifest/wellman",
  "scope": "repository",
  "created": "2026-10-21",
  "updated": "2026-10-21",
  "review_after": "2026-11-21",
  "source_revision": "d4cc5d116707addeebd319b0ef3277d4b3ab4a70",
  "affected_repositories": ["wellmanifest/wellman"],
  "evidence": ["repo://wellmanifest/wellman/src/wellman/cli.py", "repo://wellmanifest/wellman/tests/test_cli.py"]
}
---

# Project-owned document delivery

<!-- docs:section purpose -->
## Purpose

An adoption check alone cannot establish that a requested report exists in its
owning repository. The `docs` command checks placement before generation and
requires the explicit document, preparation receipt and trusted base at completion.

<!-- docs:section scope -->
## Scope

The independently pinned Docs checker owns canonical placement, metadata, index
and repository versus organization scope. Report owns report evidence and claims;
Logs owns raw event records. A recovery copy or private receipt is not a delivered
report. Under the Report contract, a project report belongs in its owning
repository's `docs/analysis/`; organization reports belong to `subactor/docs`.
Open that owner checkout before preparing organization documentation.

<!-- docs:section evidence -->
## Evidence

`tests/test_cli.py` exercises the subprocess boundary, project-relative paths,
symlink rejection, foreign checkouts, missing results, runtime drift, preservation
of existing receipts and aggregate completion failures. These checks complement
the Docs checker's own content and placement tests.

<!-- docs:section content -->
## Usage and runtime pin

The operator supplies a separately reviewed Docs package and revision; never
derive executable selection or trust pins from the candidate report. The package
directory contains `check.py`, `policy.json` and all its required relative files.
It must support both `--prepare` and `--complete`; older adoption-only runtimes
fail closed. Wellman neither fetches nor upgrades that runtime.

The package pin is SHA256 of UTF-8 JSON mapping every relative POSIX file path to
its byte SHA256, serialized with sorted keys and separators `(',', ':')`. Include
all regular files recursively; symlinks and compiled Python files are rejected.
The package is limited to 256 files and 16 MiB. Verified bytes are snapshotted
under the owner's `.subactor/receipts/docs-runtime/` for isolated execution and
removed afterwards. Python runs without site initialization or bytecode writes.

```bash
wellman docs prepare --root . --kind analysis --id result --scope repository \
  --deliverable docs/analysis/result.md --receipt .subactor/receipts/result.json \
  --docs-runtime-root "$DOCS_PACKAGE" --docs-runtime-sha256 "$DOCS_PACKAGE_SHA256" \
  --docs-standard-revision "$DOCS_REVISION"

# Generate the planned document, maintain its index, and stage the deliverables.
wellman docs complete --root . --deliverable docs/analysis/result.md \
  --prepared-plan .subactor/receipts/result.json --docs-base "$ACCEPTED_BASE" \
  --docs-runtime-root "$DOCS_PACKAGE" --docs-runtime-sha256 "$DOCS_PACKAGE_SHA256" \
  --docs-standard-revision "$DOCS_REVISION"
```

`wellman check --deliverable ...` accepts the same completion options and fails
the aggregate result if completion fails. The existing `check --actor ci` route
remains a separate governance gate. Without `--deliverable`, aggregate checks
make no document-completion claim. Preparation exclusively creates a new receipt;
it never overwrites previous evidence or generates the document itself.

<!-- docs:section limitations -->
## Limits

The destination checks cover Wellman's own artifact boundary. They do not sandbox
arbitrary shell commands or other agents, and assume no concurrent filesystem
attacker replacing directory components. A runtime digest establishes byte
identity, not reviewer authority. Receipts grant neither write leases nor merge
approval. Completion is distinct from independent publication and deployment.

<!-- docs:section next_actions -->
## Adoption

Configure the runtime and pins through the owner's reviewed delivery process,
adopt the matching Docs revision, and require explicit completion in that process.
Keep recovery evidence under the owning project's ignored operational directories.
Retain report manifests and raw Logs evidence according to their respective packs.
