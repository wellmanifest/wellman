"""Inspect analyzer pins; explicitly prepare governance environments separately.

Preflight imports distribution metadata only. Updates are a separate command;
scanning never invokes this updater. A successful stamp describes environment
preparation and grants no standard adoption, conformance or deployment trust.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from wellman.evidence import CONTRACTS, _json
from wellman.selection_contracts import ContractError, canonical_bytes, payload_digest

VERSION = "wellman.analysis-environment/v1"
PINS = {**{name: version for name, (version, _) in CONTRACTS.items()}, "sumd": "0.3.60"}
STAMP = ".last_analysis_update.json"
LOCK = ".analysis_environment.lock.json"
MAX_OUTPUT_BYTES = 1024 * 1024


def _safe(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ContractError("Environment storage must not traverse symlinks")
    return path


def _run(argv, timeout):
    """Bound process time and returned output; never run a shell or echo pip logs."""
    with tempfile.TemporaryFile() as output:
        try:
            process = subprocess.Popen(
                argv,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env={
                    k: v
                    for k, v in os.environ.items()
                    if k not in ("PYTHONPATH", "PYTHONHOME")
                },
            )
        except OSError:
            return {"exit_code": 127, "output": b"", "error": "PROCESS_UNAVAILABLE"}
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            return {"exit_code": None, "output": b"", "error": "PROCESS_TIMEOUT"}
        size = output.tell()
        output.seek(0)
        if size > MAX_OUTPUT_BYTES:
            return {
                "exit_code": code,
                "output": b"",
                "error": "PROCESS_OUTPUT_TRUNCATED",
            }
        return {"exit_code": code, "output": output.read(), "error": None}


def preflight(python, *, timeout=30):
    """Inspect exact distribution versions and sumr in this interpreter's bin dir."""
    if type(timeout) not in (int, float) or not 0 < timeout <= 30:
        raise ContractError("Preflight timeout must be between zero and 30 seconds")
    script = (
        "import importlib.metadata as m,json,sys,shutil; from pathlib import Path; result={}; "
        "\nfor name in " + repr(tuple(sorted(PINS))) + ":\n"
        " try: result[name]=m.version(name)\n"
        " except m.PackageNotFoundError: result[name]=None\n"
        'try: entries=[(e.name,e.value) for e in m.distribution("sumd").entry_points]\n'
        "except m.PackageNotFoundError: entries=[]\n"
        'print(json.dumps({"versions":result,"python":sys.version,'
        '"packages":sorted((d.metadata["Name"],d.version) for d in m.distributions()),'
        '"sumr_entrypoint":("sumr","sumd.cli:main_sumr") in entries,'
        '"sumr_executable":bool(shutil.which("sumr",path=str(Path(sys.executable).parent)))}))'
    )
    outcome = _run([str(Path(python).absolute()), "-I", "-c", script], timeout)
    report = {
        "schema": VERSION,
        "grants_authority": False,
        "ok": False,
        "pins": dict(PINS),
        "issues": [],
    }
    if outcome["exit_code"] != 0 or outcome["error"]:
        report["issues"] = [outcome["error"] or "PREFLIGHT_PROCESS_FAILED"]
        return report
    try:
        data = _json(outcome["output"])
        if set(data.get("versions", {})) != set(PINS) or not isinstance(
            data.get("packages"), list
        ):
            raise ContractError("Metadata shape mismatch")
        report["environment"] = data
        report["environment_digest"] = payload_digest(data)
        report["issues"] = [
            (
                "TOOL_MISSING:"
                if data["versions"][name] is None
                else "TOOL_VERSION_MISMATCH:"
            )
            + name
            for name, pin in PINS.items()
            if data["versions"][name] != pin
        ]
        if (
            data.get("sumr_entrypoint") is not True
            or data.get("sumr_executable") is not True
        ):
            report["issues"].append("SUMR_ENTRYPOINT_UNAVAILABLE")
        report["ok"] = not report["issues"]
    except (ValueError, ContractError):
        report["issues"] = ["PREFLIGHT_METADATA_INVALID"]
    return report


def _atomic(path, document):
    _safe(path)
    temporary = path.parent / ("." + path.name + "." + str(os.getpid()) + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(canonical_bytes(document))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def update_environment(environment, *, timeout=300):
    """Explicit Unix-only preparation; write success stamp after every check.

    An existing non-venv directory is preserved. Installation failure may leave
    a partially changed environment, but never a new success stamp. The previous
    source observation remains independent of this installation operation.
    """
    import fcntl

    if type(timeout) not in (int, float) or not 0 < timeout <= 600:
        raise ContractError("Update timeout must be between zero and 600 seconds")
    environment = _safe(environment)
    environment.mkdir(parents=True, exist_ok=True)
    marker = _safe(environment / "pyvenv.cfg")
    if not marker.is_file() and any(environment.iterdir()):
        raise ContractError(
            "Preserve nonempty directory without a virtual-environment marker"
        )
    _safe(environment / "bin")
    _safe(environment / STAMP)
    _safe(environment / LOCK)
    lock_path = _safe(environment / ".wellman-update.lock")
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    result = {
        "schema": VERSION,
        "grants_authority": False,
        "ok": False,
        "success_stamp_written": False,
    }
    with os.fdopen(descriptor, "a+b") as lock:
        deadline = time.monotonic() + 30
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    return dict(result, error="ENVIRONMENT_UPDATE_BUSY")
                time.sleep(0.05)
        if not marker.is_file():
            outcome = _run(
                [sys.executable, "-I", "-m", "venv", str(environment)], min(timeout, 60)
            )
            if outcome["exit_code"] != 0 or outcome["error"]:
                return dict(result, error="VENV_CREATION_FAILED")
        python = environment / "bin/python"
        identity = _run(
            [
                str(python),
                "-I",
                "-c",
                'import sys,json; print(json.dumps({"prefix":sys.prefix,"base_prefix":sys.base_prefix}))',
            ],
            30,
        )
        if identity["exit_code"] != 0 or identity["error"]:
            return dict(result, error="ENVIRONMENT_IDENTITY_UNAVAILABLE")
        identity = _json(identity["output"])
        if identity.get("prefix") != str(environment) or identity.get(
            "base_prefix"
        ) == identity.get("prefix"):
            return dict(result, error="ENVIRONMENT_IS_NOT_ISOLATED")
        outcome = _run(
            [
                str(python),
                "-I",
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--quiet",
                "--disable-pip-version-check",
                "--no-input",
                *[name + "==" + pin for name, pin in sorted(PINS.items())],
            ],
            timeout,
        )
        if outcome["exit_code"] != 0 or outcome["error"]:
            return dict(
                result, error="PINNED_INSTALL_FAILED", process_error=outcome["error"]
            )
        checked = preflight(python)
        if not checked["ok"]:
            return dict(
                result, error="POST_INSTALL_PREFLIGHT_FAILED", preflight=checked
            )
        receipt = {
            "schema": VERSION,
            "grants_authority": False,
            "pins": dict(PINS),
            "environment": checked["environment"],
            "environment_digest": checked["environment_digest"],
        }
        _atomic(environment / LOCK, receipt)
        _atomic(
            environment / STAMP,
            {
                "schema": VERSION,
                "grants_authority": False,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "lock_digest": payload_digest(receipt),
            },
        )
        return dict(
            result,
            ok=True,
            success_stamp_written=True,
            lock_digest=payload_digest(receipt),
            environment_digest=checked["environment_digest"],
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    observe = commands.add_parser("preflight")
    observe.add_argument("--python", required=True)
    update = commands.add_parser("update")
    update.add_argument("--environment", required=True)
    args = parser.parse_args(argv)
    try:
        result = (
            preflight(args.python)
            if args.command == "preflight"
            else update_environment(args.environment)
        )
    except (OSError, ValueError, ImportError) as error:
        result = {
            "schema": VERSION,
            "grants_authority": False,
            "ok": False,
            "error": type(error).__name__,
        }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
