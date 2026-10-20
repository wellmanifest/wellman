"""Checkout-bound Python/pytest execution, independent of static conformance.

The admission boundary controls this launch, not arbitrary filesystem effects
of the program. It grants neither a writer lease nor publication authority.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from wellman.adoption import repository_root, safe_path


class ExecutionError(ValueError):
    """A command cannot be associated with the requested checkout."""


def _git(root, *arguments):
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("GIT_") or key == "GIT_CEILING_DIRECTORIES"}
    result = subprocess.run(
        ["git", "-C", str(root), *arguments], env=environment,
        capture_output=True, check=True, timeout=10,
    )
    return result.stdout


def _identity(requested):
    root = repository_root(requested)
    records = _git(root, "worktree", "list", "--porcelain", "-z").split(b"\0\0")
    checkouts = []
    for record in records:
        first = record.split(b"\0", 1)[0]
        if first.startswith(b"worktree "):
            checkouts.append(safe_path(os.fsdecode(first[len(b"worktree "):])))
    if not checkouts or root not in checkouts:
        raise ExecutionError("Requested checkout is not registered with Git")
    return root, checkouts[0], _git(root, "rev-parse", "HEAD").decode().strip()


def _environment(root, primary, allow_primary):
    candidates = [root / ".venv"]
    if allow_primary and primary != root:
        candidates.append(primary / ".venv")
    for candidate in candidates:
        # Reject a redirected candidate even when another environment exists.
        candidate = safe_path(candidate)
        if not candidate.exists():
            continue
        configuration = safe_path(candidate / "pyvenv.cfg")
        bin_dir = safe_path(candidate / ("Scripts" if os.name == "nt" else "bin"))
        python = bin_dir / ("python.exe" if os.name == "nt" else "python")
        if not configuration.is_file() or not python.is_file():
            raise ExecutionError("Project .venv is incomplete; prepare it before execution")
        return candidate, python
    raise ExecutionError(
        "Missing checkout .venv; prepare it locally, or explicitly use "
        "--allow-primary-venv for this repository's registered primary checkout"
    )


def _command(arguments, root, venv, python):
    if not arguments:
        raise ExecutionError("A Python or pytest command is required after --")
    program = arguments[0]
    name = Path(program).name
    is_python = re.fullmatch(r"python(?:\d+(?:\.\d+)?)?(?:\.exe)?", name)
    is_pytest = name in {"pytest", "pytest.exe"}
    if not is_python and not is_pytest:
        raise ExecutionError("This execution profile accepts Python and pytest only")
    if is_python and name not in {"python", "python3", "python.exe"}:
        if not (python.parent / name).is_file():
            raise ExecutionError("Requested Python version is unavailable in the project .venv")
    if Path(program).is_absolute() or Path(program).parent != Path("."):
        path = Path(program) if Path(program).is_absolute() else root / program
        parent = safe_path(path.parent)
        if parent != python.parent or not path.is_file():
            raise ExecutionError("Interpreter/entry point belongs to another environment")
    return [str(python), *(["-m", "pytest"] if is_pytest else []), *arguments[1:]]


def _child_environment(root, venv, python, scratch):
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith("GIT_") and key not in {
            "PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "PYTHONPYCACHEPREFIX",
            "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV",
        }
    }
    environment.update({
        "TMPDIR": str(scratch), "TEMP": str(scratch), "TMP": str(scratch),
        "VIRTUAL_ENV": str(venv), "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PATH": str(python.parent) + os.pathsep + os.environ.get("PATH", os.defpath),
        # A non-Git fixture below local TMPDIR must not discover the real
        # checkout above the cache and accidentally adopt/mutate that checkout.
        "GIT_CEILING_DIRECTORIES": str(scratch),
    })
    # Explicit candidate source only; never import a sibling/primary checkout
    # through an inherited PYTHONPATH. Dependencies remain in the admitted venv.
    source = root / "src"
    if source.is_dir():
        environment["PYTHONPATH"] = str(safe_path(source))
    return environment


def prepare(requested, arguments, *, allow_primary=False):
    """Read-only admission: identify Git, interpreter and ignored scratch owner."""
    root, primary, head = _identity(requested)
    venv, python = _environment(root, primary, allow_primary)
    command = _command(arguments, root, venv, python)
    cache = safe_path(root / ".subactor" / "cache" / "execution")
    try:
        ignored = _git(root, "check-ignore", "--no-index", "--", ".subactor/cache/execution/")
    except subprocess.CalledProcessError as error:
        raise ExecutionError("Checkout must ignore /.subactor/cache/ before execution") from error
    if not ignored:
        raise ExecutionError("Checkout must ignore /.subactor/cache/ before execution")
    environment = _child_environment(root, venv, python, cache)
    probe = subprocess.run(
        [str(python), "-I", "-c", "import json,sys; print(json.dumps(sys.prefix))"],
        cwd=root, env=environment, capture_output=True, text=True, timeout=10, check=True,
    )
    if Path(json.loads(probe.stdout)).resolve() != venv:
        raise ExecutionError("Interpreter does not report the admitted virtual environment")
    return {
        "schema": "wellman.project-execution/v1", "checkout": str(root),
        "primary_checkout": str(primary), "head_sha": head,
        "venv": str(venv), "interpreter": str(python), "cache": str(cache),
        "primary_venv_reused": venv == primary / ".venv" and root != primary,
        "source_binding": "dirty_worktree_not_attested" if _git(
            root, "status", "--porcelain", "--untracked-files=normal"
        ).strip() else "clean_head",
        "command_sha256": hashlib.sha256(json.dumps(command).encode()).hexdigest(),
        "filesystem_sandbox": "not_applied", "status": "admitted",
    }, command


def _private_run(cache):
    # Validate every existing path component before creating local state.
    safe_path(cache)
    for directory in reversed([cache, *cache.parents]):
        if directory.exists():
            if not directory.is_dir():
                raise ExecutionError("Execution cache has a non-directory component")
        else:
            directory.mkdir(mode=0o700, exist_ok=True)
        safe_path(directory)
    run = cache / uuid.uuid4().hex
    run.mkdir(mode=0o700)
    (run / "tmp").mkdir(mode=0o700)
    return run


def execute(requested, arguments, *, allow_primary=False, dry_run=False):
    """Launch in the admitted checkout; preserve the real child's exit status."""
    context, command = prepare(requested, arguments, allow_primary=allow_primary)
    if dry_run:
        print(json.dumps(context, indent=2))
        return 0
    run = _private_run(Path(context["cache"]))
    context.update({"run_id": run.name, "tmpdir": str(run / "tmp"),
                    "started_at": datetime.now(timezone.utc).isoformat(), "status": "running"})
    receipt = run / "context.json"
    # This private record intentionally excludes raw argv, stdout and env.
    with receipt.open("x", encoding="utf-8") as stream:
        os.chmod(receipt, 0o600)
        json.dump(context, stream, indent=2)
    environment = _child_environment(
        Path(context["checkout"]), Path(context["venv"]),
        Path(context["interpreter"]), run / "tmp",
    )
    print(f"Wellman execution context: {receipt}", file=sys.stderr, flush=True)
    try:
        result = subprocess.run(command, cwd=context["checkout"], env=environment, check=False)
        context.update(status="succeeded" if result.returncode == 0 else "failed",
                       exit_code=result.returncode)
        return result.returncode if result.returncode >= 0 else 128 - result.returncode
    except BaseException:
        context["status"] = "interrupted"
        raise
    finally:
        context["finished_at"] = datetime.now(timezone.utc).isoformat()
        receipt.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")


def add_parser(subparsers):
    parser = subparsers.add_parser("run", help="Run Python/pytest with checkout-bound .venv and scratch")
    parser.add_argument("--root", "-r", default=".")
    parser.add_argument("--allow-primary-venv", action="store_true",
                        help="Explicitly reuse .venv of this Git repository's primary checkout")
    parser.add_argument("--dry-run", action="store_true", help="Check admission without creating scratch or running the command")
    parser.add_argument("argv", nargs=argparse.REMAINDER)
    parser.set_defaults(func=run)


def run(args):
    command = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
    try:
        return execute(args.root, command, allow_primary=args.allow_primary_venv, dry_run=args.dry_run)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        # Avoid echoing command/provider stderr, which may contain credentials.
        detail = str(error) if isinstance(error, ValueError) else type(error).__name__
        print(f"GOV-EXECUTION-001: {detail}", file=sys.stderr)
        return 2
