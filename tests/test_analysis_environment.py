import json
import sys

import pytest

import wellman.analysis_environment as module
from wellman.selection_contracts import ContractError, canonical_bytes, payload_digest


def metadata(**extra):
    return {
        "versions": dict(module.PINS),
        "packages": [[k, v] for k, v in sorted(module.PINS.items())],
        "python": "fixture",
        "sumr_entrypoint": True,
        "sumr_executable": True,
        **extra,
    }


def outcome(data=None, code=0, error=None):
    return {"exit_code": code, "error": error, "output": canonical_bytes(data or {})}


def test_preflight_uses_isolated_metadata_and_has_no_install_effect(monkeypatch):
    calls = []

    def run(argv, timeout):
        calls.append(argv)
        return outcome(metadata())

    monkeypatch.setattr(module, "_run", run)
    result = module.preflight("/example/bin/python")
    assert result["ok"] and not result["grants_authority"]
    assert result["environment_digest"] == payload_digest(metadata())
    assert calls[0][1:3] == ["-I", "-c"] and "importlib.metadata" in calls[0][-1]
    assert "pip" not in calls[0] and not any("import code2llm" in p for p in calls[0])


@pytest.mark.parametrize(
    "changed", ["missing", "version", "entrypoint", "executable", "metadata"]
)
def test_preflight_distinguishes_missing_unsupported_and_unavailable_sumr(
    monkeypatch, changed
):
    data = metadata()
    if changed == "missing":
        data["versions"]["prefact"] = None
    elif changed == "version":
        data["versions"]["redup"] = "unrecognized"
    elif changed == "entrypoint":
        data["sumr_entrypoint"] = False
    elif changed == "executable":
        data["sumr_executable"] = False
    else:
        data["versions"] = {}
    monkeypatch.setattr(module, "_run", lambda *args: outcome(data))
    result = module.preflight(sys.executable)
    assert not result["ok"] and result["issues"] and not result["grants_authority"]


@pytest.mark.parametrize(
    "error", ["PROCESS_TIMEOUT", "PROCESS_UNAVAILABLE", "PROCESS_OUTPUT_TRUNCATED"]
)
def test_preflight_process_failures_are_diagnostic(monkeypatch, error):
    monkeypatch.setattr(module, "_run", lambda *args: outcome(code=None, error=error))
    result = module.preflight(sys.executable)
    assert not result["ok"] and result["issues"] == [error]


@pytest.fixture
def environment(tmp_path, monkeypatch):
    root = tmp_path / "tools"
    root.mkdir()
    (root / "bin").mkdir()
    (root / "pyvenv.cfg").write_text("home=/fixture\n")
    calls = []

    def run(argv, timeout):
        calls.append(argv)
        if "pip" in argv:
            return outcome()
        return outcome({"prefix": str(root), "base_prefix": "/base"})

    monkeypatch.setattr(module, "_run", run)
    monkeypatch.setattr(
        module,
        "preflight",
        lambda *args: {
            "ok": True,
            "environment": metadata(),
            "environment_digest": payload_digest(metadata()),
        },
    )
    return root, calls


def test_explicit_update_installs_exact_pins_and_stamps_only_validated_environment(
    environment,
):
    root, calls = environment
    result = module.update_environment(root)
    assert (
        result["ok"]
        and result["success_stamp_written"]
        and not result["grants_authority"]
    )
    pip = next(argv for argv in calls if "pip" in argv)
    assert pip[1:4] == ["-I", "-m", "pip"]
    assert {x for x in pip if "==" in x} == {
        k + "==" + v for k, v in module.PINS.items()
    }
    lock = json.loads((root / module.LOCK).read_text())
    stamp = json.loads((root / module.STAMP).read_text())
    assert stamp["lock_digest"] == payload_digest(lock) == result["lock_digest"]
    assert lock["environment"]["packages"] == metadata()["packages"]


@pytest.mark.parametrize(
    "failure",
    ["install", "postflight", "identity", "timeout", "lock-write", "stamp-write"],
)
def test_failed_update_preserves_previous_success_stamp(
    environment, monkeypatch, failure
):
    root, _ = environment
    (root / module.STAMP).write_text("previous-success\n")
    original = module._run
    if failure in ("install", "identity", "timeout"):

        def run(argv, timeout):
            if "pip" in argv and failure in ("install", "timeout"):
                return outcome(
                    code=1, error="PROCESS_TIMEOUT" if failure == "timeout" else None
                )
            if failure == "identity":
                return outcome({"prefix": "/base", "base_prefix": "/base"})
            return original(argv, timeout)

        monkeypatch.setattr(module, "_run", run)
    elif failure == "postflight":
        monkeypatch.setattr(
            module,
            "preflight",
            lambda *args: {"ok": False, "issues": ["SUMR_ENTRYPOINT_UNAVAILABLE"]},
        )
    else:
        atomic = module._atomic

        def fail(path, data):
            if path.name == (module.LOCK if failure == "lock-write" else module.STAMP):
                raise OSError("Write failed")
            atomic(path, data)

        monkeypatch.setattr(module, "_atomic", fail)
    try:
        result = module.update_environment(root)
    except OSError:
        result = {"ok": False}
    assert not result["ok"]
    assert (root / module.STAMP).read_text() == "previous-success\n"


def test_update_refuses_unknown_directory_and_symlink_without_execution(
    tmp_path, monkeypatch
):
    calls = []
    monkeypatch.setattr(module, "_run", lambda *args: calls.append(args))
    unknown = tmp_path / "unknown"
    unknown.mkdir()
    (unknown / "keep.txt").write_text("keep")
    with pytest.raises(ContractError):
        module.update_environment(unknown)
    linked = tmp_path / "linked"
    linked.symlink_to(unknown, target_is_directory=True)
    with pytest.raises(ContractError):
        module.update_environment(linked)
    assert not calls and (unknown / "keep.txt").read_text() == "keep"


def test_update_refuses_symlink_stamp_without_installing(environment, tmp_path):
    root, calls = environment
    other = tmp_path / "keep.json"
    other.write_text("keep")
    (root / module.STAMP).symlink_to(other)
    with pytest.raises(ContractError):
        module.update_environment(root)
    assert not calls and other.read_text() == "keep"


def test_readonly_actual_preflight_does_not_import_analyzer_modules(tmp_path):
    before = list(tmp_path.iterdir())
    result = module.preflight(sys.executable)
    assert result["schema"] == module.VERSION and not result["grants_authority"]
    assert "environment_digest" in result or result["issues"]
    assert list(tmp_path.iterdir()) == before


def test_cli_preflight_outputs_diagnostics_and_never_calls_updater(monkeypatch, capsys):
    monkeypatch.setattr(
        module,
        "preflight",
        lambda *args: {
            "schema": module.VERSION,
            "ok": False,
            "issues": ["TOOL_MISSING:prefact"],
            "grants_authority": False,
        },
    )
    monkeypatch.setattr(
        module, "update_environment", lambda *args: pytest.fail("Implicit update")
    )
    assert module.main(["preflight", "--python", sys.executable]) == 1
    assert json.loads(capsys.readouterr().out)["issues"] == ["TOOL_MISSING:prefact"]


@pytest.mark.parametrize("timeout", [0, -1, True, float("nan"), 601])
def test_invalid_update_budget_fails_before_effects(tmp_path, timeout):
    with pytest.raises(ContractError):
        module.update_environment(tmp_path / "missing", timeout=timeout)
    assert not (tmp_path / "missing").exists()


def test_failed_explicit_venv_creation_has_no_success_stamp(tmp_path, monkeypatch):
    calls = []

    def run(argv, timeout):
        calls.append(argv)
        return outcome(code=1)

    monkeypatch.setattr(module, "_run", run)
    root = tmp_path / "new-environment"
    result = module.update_environment(root)
    assert (
        result["error"] == "VENV_CREATION_FAILED"
        and not result["success_stamp_written"]
    )
    assert calls[0][1:4] == ["-I", "-m", "venv"]
    assert not (root / module.STAMP).exists() and not any(
        "pip" in argv for argv in calls
    )


def test_busy_update_lock_is_bounded_and_does_not_take_over(environment, monkeypatch):
    import fcntl

    root, calls = environment

    def busy(*args):
        raise BlockingIOError()

    times = iter([0, 31])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(fcntl, "flock", busy)
    result = module.update_environment(root)
    assert result["error"] == "ENVIRONMENT_UPDATE_BUSY" and not calls
    assert not (root / module.STAMP).exists()


def test_parallel_explicit_updates_serialize_installation(environment, monkeypatch):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    root, _ = environment
    original = module._run
    guard = threading.Lock()
    active = [0]
    maximum = [0]

    def run(argv, timeout):
        if "pip" not in argv:
            return original(argv, timeout)
        with guard:
            active[0] += 1
            maximum[0] = max(maximum[0], active[0])
        time.sleep(0.05)
        with guard:
            active[0] -= 1
        return outcome()

    monkeypatch.setattr(module, "_run", run)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: module.update_environment(root), range(2)))
    assert all(r["ok"] for r in results) and maximum == [1]
    assert json.loads((root / module.STAMP).read_text())[
        "lock_digest"
    ] == payload_digest(json.loads((root / module.LOCK).read_text()))


def test_actual_process_output_is_bounded():
    result = module._run(
        [
            sys.executable,
            "-I",
            "-c",
            'import sys; sys.stdout.write("x"*'
            + str(module.MAX_OUTPUT_BYTES + 1)
            + ")",
        ],
        5,
    )
    assert result["error"] == "PROCESS_OUTPUT_TRUNCATED" and result["output"] == b""


def test_timeout_kills_descendants_before_they_can_write(tmp_path):
    import time

    marker = tmp_path / "late.txt"
    child = (
        "import time; from pathlib import Path; time.sleep(0.5); Path("
        + repr(str(marker))
        + ').write_text("late")'
    )
    parent = (
        'import subprocess,sys,time; subprocess.Popen([sys.executable,"-I","-c",'
        + repr(child)
        + "]); time.sleep(5)"
    )
    result = module._run([sys.executable, "-I", "-c", parent], 0.2)
    assert result["error"] == "PROCESS_TIMEOUT"
    time.sleep(0.6)
    assert not marker.exists()
