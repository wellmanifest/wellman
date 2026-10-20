---
{
  "schema": "wellmanifest.docs/document/v1",
  "id": "project-execution",
  "kind": "information",
  "version": 1,
  "title": "Project-bound Python execution and enforcement boundaries",
  "status": "proposed",
  "owner": "wellmanifest/wellman",
  "created": "2026-10-20",
  "updated": "2026-10-20",
  "review_after": "2026-11-20",
  "source_revision": "70edd469cbea3e417baafe6af78566bd06d34eb6",
  "affected_repositories": ["wellmanifest/wellman", "paxlet-com/willman"],
  "evidence": [
    "repo://wellmanifest/wellman@00424b09c919c757442874f040a7848370776221/src/wellman/execution.py",
    "repo://wellmanifest/wellman@00424b09c919c757442874f040a7848370776221/tests/test_execution.py",
    "https://github.com/wellmanifest/new-project/issues/501"
  ]
}
---

# Project-bound Python execution

<!-- docs:section purpose -->
## Purpose and observed failure

This is a proposed execution profile. Its candidate implementation is
[Wellman PR #66](https://github.com/wellmanifest/wellman/pull/66), source
`00424b09c919c757442874f040a7848370776221`; publication of this proposal does
not deploy that runtime or enroll executors.

A static governance PASS verifies selected repository rules. It does not
intercept shell commands, observe their interpreter or prove runtime isolation.
Code, execution context, dependency provenance, actual test results and trusted
publication are separate observations.

A Willman test invocation used its canonical ticket worktree and the same
project's primary `.venv`, but placed temporary files in a shared host state
directory after `/tmp` filled. The test assertion failure in that invocation
was independently corrected; it was not caused by the temporary-directory
location. The shared temporary directory nevertheless lacked a per-checkout
execution boundary and did not satisfy this local development profile.

<!-- docs:section scope -->
## Execution profile

Use the reviewed `wellman run` launcher for Python and pytest commands:

```bash
.venv/bin/wellman run --root . -- python -m pytest -q tests/test_feature.py
.venv/bin/wellman run --root . --dry-run -- pytest -q
```

The invoking Wellman runtime must itself be the expected reviewed version.
`--dry-run` checks admission without launching the requested command or
creating run state. It probes the selected Python environment to establish
its actual prefix; it is not a promise to execute no subprocesses.

The profile requires:

1. **Checkout identity.** Resolve nested requests to the actual Git checkout;
   discover its registered primary through Git. Ignore inherited Git location
   selectors. Reject nonexistent, non-Git and symlinked requested paths.
2. **Interpreter association.** Use this checkout's real `.venv` and verify
   `sys.prefix`. Never silently use global Python or another project's venv.
   Missing or incomplete environments fail before the requested command.
   Preparation and dependency installation are separate authorized actions.
3. **Explicit reuse.** `--allow-primary-venv` permits reuse of the registered
   primary's `.venv` only when the current checkout has no environment. A
   current-checkout environment takes precedence. A redirected environment
   fails rather than falling back. Explicit interpreter paths must match the
   admitted environment. Dependencies remain those of that environment;
   this is not lockfile or package-inventory attestation.
4. **Local scratch.** Each invocation owns a private unique directory at
   `<checkout>/.subactor/cache/execution/<run-id>/`, with its `tmp/` beneath it.
   Require Git to ignore this cache and reject symlinked components before
   creating it. Set `TMPDIR`, `TEMP` and `TMP` to that run's temporary directory.
   Do not change daemon storage, historical receipts or another run's files.
5. **Candidate imports.** Remove inherited Python home/import/user-site
   overrides, disable user site and bytecode writes, and add only the candidate
   checkout's conventional `src/` to `PYTHONPATH`. Preserve other declared
   process policy inputs. Prefix PATH with the selected environment.
6. **Fixture boundary.** Set Git's discovery ceiling at local temporary storage.
   Real nested Git fixtures keep their identity; non-Git fixtures cannot
   discover and accidentally modify the containing development checkout.
   Bootstrap metadata inspection must honor that same ceiling.
7. **Observed result.** Preserve the actual child exit code. A private
   `context.json` records checkout, primary, HEAD, interpreter, environment,
   scratch, command digest, timestamps and result. Dirty source is explicitly
   unverified. Do not put raw command arguments, provider output or environment
   secrets in this context receipt. Retention requires a separate owner policy;
   successful execution does not authorize deleting unknown run state.

For intentional same-project reuse from a linked checkout:

```bash
# WELLMAN_BIN names the independently reviewed launcher; it is tooling,
# not the interpreter selected for the project being tested.
"$WELLMAN_BIN" run --root "$PWD" --allow-primary-venv -- \
  python -m pytest -q tests/test_feature.py
```

The normal venv Python executable may be a symlink to its base interpreter.
That alone does not make the venv foreign: its parent directories and
`pyvenv.cfg` must be local and `sys.prefix` must identify the admitted venv.
Rejecting all external path strings would incorrectly reject ordinary Python
venvs and independently installed immutable tools.

<!-- docs:section limitations -->
## Required adapter adoption and limits

This profile admits a Python/pytest launch and controls its initial context.
It is not an operating-system sandbox: Python code, dependencies, explicit
output arguments or child processes can perform other authorized or
unauthorized effects. Shell entrypoints are refused by this profile; it does
not yet define equivalent Node, Rust or arbitrary shell profiles. Execution
leases, canonical Worktrees conformance, secret policy, filesystem/network
confinement and independent validation remain separate requirements.

An executor must mediate its Python launches through the admitted implementation
and verify its bound result before claiming this profile is enforced. A static
`wellman check` cannot truthfully report that an arbitrary earlier shell
command was mediated. Its existing `runtime_enforcement=not_checked` remains
appropriate. An optional launcher alone does not establish mandatory fleet
coverage; adding prose to an agent prompt does not close that gap.

On the investigated host, the global `wellman` entrypoint was the bundled
checker from `wellmanifest/new-project/packages/wellman` v0.20.92, not this
repository's CLI. Both distributions use the same package name. Do not replace
that global installation merely to expose `run`: protected CI depends on its
checker arguments and immutable pins. Use an explicitly selected project
runtime for qualification. Converging the entrypoints, publishing managed
instructions and enrolling executors are tracked in
[new-project #501](https://github.com/wellmanifest/new-project/issues/501).
That owner's existing workstream must finish before the dependent change.

External immutable tool installations, credentials and protected controller
receipt stores keep their declared ownership. They are not development scratch
and this profile authorizes no data migration or blanket ban on those paths.

<!-- docs:section evidence -->
## Qualification

The ticket-067 implementation was tested through its own checkout `.venv` and
local scratch: **206 affected tests passed, with 8 existing optional skips**.
Regression cases cover foreign interpreters, implicit primary reuse, nested
requests, candidate imports, unavailable Python versions, symlink redirection,
unignored caches, concurrent runs and actual nonzero child exit status. The
managed governance gate passed.

The real Willman ticket-289 suites passed **18 tests and 8 subtests** through
the launcher, with explicit same-project primary-venv reuse and scratch below
that ticket's checkout. This proves those invocations; it does not prove that
all Willman, IDE, shell or OneDev launches already use this profile. Source
publication and deployed runtime enrollment must each retain their own evidence.
