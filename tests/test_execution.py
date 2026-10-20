"""Real process regressions for checkout, environment and scratch admission."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import venv

import pytest

from wellman.cli import main
from wellman.execution import ExecutionError, execute, prepare, run


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project with spaces"
    root.mkdir()
    git(root, "init", "-q")
    (root / ".gitignore").write_text("/.venv/\n/.subactor/cache/\n/.worktrees/\n")
    git(root, "add", ".gitignore")
    git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
        "-c", "core.hooksPath=/dev/null", "commit", "-qm", "fixture")
    return root


def environment(root):
    target = root / ".venv"
    venv.EnvBuilder(with_pip=False).create(target)
    return target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def receipts(root):
    return [json.loads(p.read_text()) for p in
            (root / ".subactor/cache/execution").glob("*/context.json")]


def probe_command():
    return ["python", "-c", """
import json, os, pathlib, sys, tempfile
p = pathlib.Path('observed.json')
p.write_text(json.dumps(dict(cwd=os.getcwd(), prefix=sys.prefix,
    tmp=tempfile.gettempdir(), home=os.getenv('PYTHONHOME'),
    pythonpath=os.getenv('PYTHONPATH'), temp=os.getenv('TEMP'),
    git_dir=os.getenv('GIT_DIR'), user_site=sys.flags.no_user_site)))
with tempfile.NamedTemporaryFile() as f:
    assert pathlib.Path(f.name).parent == pathlib.Path(os.environ['TMPDIR'])
"""]


def test_nested_launch_uses_actual_checkout_and_local_temporary_directory(project, monkeypatch):
    python = environment(project)
    nested = project / "docs"
    nested.mkdir()
    monkeypatch.setenv("TMPDIR", "/external/shared/tmp")
    monkeypatch.setenv("TEMP", "/another/project")
    monkeypatch.setenv("PYTHONHOME", "/unusable/python")
    monkeypatch.setenv("PYTHONPATH", "/unrelated/candidate")
    monkeypatch.setenv("GIT_DIR", "/unrelated/.git")
    assert execute(nested, probe_command()) == 0
    observed = json.loads((project / "observed.json").read_text())
    report, = receipts(project)
    assert observed["cwd"] == str(project)
    assert observed["prefix"] == str(project / ".venv")
    assert Path(observed["tmp"]).is_relative_to(project / ".subactor/cache/execution")
    assert observed["temp"] == observed["tmp"]
    assert observed["home"] is None and observed["pythonpath"] is None
    assert observed["git_dir"] is None and observed["user_site"] == 1
    assert report["interpreter"] == str(python)
    assert report["status"] == "succeeded" and report["exit_code"] == 0
    assert report["filesystem_sandbox"] == "not_applied"
    assert "argv" not in report and "environment" not in report
    if os.name != "nt":
        receipt = next((project / ".subactor/cache/execution").glob("*/context.json"))
        assert receipt.stat().st_mode & 0o777 == 0o600
        assert receipt.parent.stat().st_mode & 0o777 == 0o700


def test_foreign_interpreter_is_refused_before_execution(project, tmp_path):
    environment(project)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    python = environment(foreign)
    with pytest.raises(ExecutionError, match="another environment"):
        execute(project, [str(python), "-c", "raise Exception('must not run')"])
    assert not (project / ".subactor/cache").exists()


def test_primary_environment_requires_explicit_verified_reuse(project):
    python = environment(project)
    linked = project / ".worktrees/ticket-001--fixture"
    git(project, "worktree", "add", "-qb", "ticket/001-fixture", str(linked))
    with pytest.raises(ExecutionError, match="Missing checkout"):
        execute(linked, probe_command())
    assert execute(linked, probe_command(), allow_primary=True) == 0
    report, = receipts(linked)
    assert report["primary_checkout"] == str(project)
    assert report["primary_venv_reused"] is True
    assert report["interpreter"] == str(python)
    assert Path(report["tmpdir"]).is_relative_to(linked)
    assert not (project / "observed.json").exists()


def test_checkout_venv_precedes_primary_even_with_opt_in(project):
    environment(project)
    linked = project / ".worktrees/ticket-002--fixture"
    git(project, "worktree", "add", "-qb", "ticket/002-fixture", str(linked))
    python = environment(linked)
    context, command = prepare(linked, ["python", "-c", "pass"], allow_primary=True)
    assert command[0] == str(python)
    assert not context["primary_venv_reused"]


@pytest.mark.parametrize("component", [".venv", ".subactor", ".subactor/cache"])
def test_symlinked_environment_or_scratch_is_refused(project, tmp_path, component):
    outside = tmp_path / "outside"
    outside.mkdir()
    if component == ".venv":
        environment(outside)
        target = outside / ".venv"
    else:
        environment(project)
        target = outside
    link = project / component
    link.parent.mkdir(exist_ok=True)
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        execute(project, probe_command())
    assert not (outside / "execution").exists()


def test_root_alias_and_non_git_root_are_refused(project, tmp_path):
    environment(project)
    alias = tmp_path / "alias"
    alias.symlink_to(project, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        execute(alias, probe_command())
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(ValueError):
        execute(plain, probe_command())


def test_missing_or_broken_environment_does_not_fall_back_to_global(project):
    with pytest.raises(ExecutionError, match="Missing checkout"):
        execute(project, ["python", "-c", "pass"])
    (project / ".venv").mkdir()
    with pytest.raises(ExecutionError, match="incomplete"):
        execute(project, ["python", "-c", "pass"])


def test_unignored_cache_is_refused(project):
    environment(project)
    (project / ".gitignore").write_text("/.venv/\n")
    with pytest.raises(ExecutionError, match="must ignore"):
        execute(project, probe_command())
    assert not (project / ".subactor").exists()


def test_real_nonzero_exit_is_preserved_in_receipt(project):
    environment(project)
    assert execute(project, ["python", "-c", "raise SystemExit(7)"]) == 7
    report, = receipts(project)
    assert report["status"] == "failed" and report["exit_code"] == 7


def test_tool_caches_override_inherited_paths_and_persist_between_runs(project, tmp_path, monkeypatch):
    environment(project)
    names = ("XDG_CACHE_HOME", "PIP_CACHE_DIR", "UV_CACHE_DIR")
    foreign = tmp_path / "another project's cache"
    foreign.mkdir()
    for name in names:
        monkeypatch.setenv(name, str(foreign))
    command = ["python", "-c", """
import os, pathlib
for name in ('XDG_CACHE_HOME', 'PIP_CACHE_DIR', 'UV_CACHE_DIR'):
    directory = pathlib.Path(os.environ[name])
    assert directory.is_relative_to(pathlib.Path.cwd())
    marker = directory / 'counter'
    marker.write_text(str(int(marker.read_text()) + 1) if marker.exists() else '1')
"""]
    assert execute(project, command) == 0
    assert execute(project, command) == 0
    reports = receipts(project)
    assert len(reports) == 2
    assert reports[0]["tool_caches"] == reports[1]["tool_caches"]
    assert reports[0]["tmpdir"] != reports[1]["tmpdir"]
    assert set(reports[0]["tool_caches"]) == set(names)
    for directory in reports[0]["tool_caches"].values():
        path = Path(directory)
        assert path.is_relative_to(project / ".subactor/cache/execution/tools")
        assert (path / "counter").read_text() == "2"
        if os.name != "nt":
            assert path.stat().st_mode & 0o777 == 0o700
    assert list(foreign.iterdir()) == []


@pytest.mark.parametrize("component", ["tools", "tools/xdg", "tools/pip", "tools/uv"])
@pytest.mark.parametrize("redirect", [True, False], ids=["symlink", "file"])
def test_invalid_tool_cache_fails_before_launch(project, tmp_path, component, redirect):
    environment(project)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_text("preserve")
    target = project / ".subactor/cache/execution" / component
    target.parent.mkdir(parents=True)
    if redirect:
        target.symlink_to(outside, target_is_directory=True)
    else:
        target.write_text("preserve")
    with pytest.raises(ValueError, match="symlink|non-directory"):
        execute(project, probe_command())
    assert not (project / "observed.json").exists()
    assert receipts(project) == []
    assert sentinel.read_text() == "preserve"
    assert list(outside.iterdir()) == [sentinel]


def test_parallel_commands_own_distinct_scratch(project):
    environment(project)
    command = ["python", "-c", "import tempfile; tempfile.TemporaryFile().close()"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: execute(project, command), range(2))) == [0, 0]
    reports = receipts(project)
    assert len(reports) == 2
    assert len({report["tmpdir"] for report in reports}) == 2


def test_dry_run_does_not_create_operational_state_and_cli_executes(project, capsys):
    environment(project)
    assert main(["run", "--root", str(project), "--dry-run", "--", "pytest", "-q"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "admitted"
    assert not (project / ".subactor").exists()
    assert main(["run", "--root", str(project), "--", "python", "-c", "raise SystemExit(3)"]) == 3


def test_unsupported_shell_and_foreign_executable_cannot_bypass_profile(project, capsys):
    environment(project)
    args = argparse.Namespace(root=project, argv=["--", "bash", "-c", "exit 0"],
                              allow_primary_venv=False, dry_run=False)
    assert run(args) == 2
    assert "GOV-EXECUTION-001" in capsys.readouterr().err
    assert not (project / ".subactor").exists()


def test_requested_python_version_is_not_silently_replaced(project):
    environment(project)
    with pytest.raises(ExecutionError, match="version is unavailable"):
        execute(project, ["python9.99", "-c", "pass"])


def test_local_source_is_selected_without_importing_primary_source(project):
    environment(project)
    (project / "src").mkdir()
    (project / "src/marker.py").write_text("value = 'primary'\n")
    git(project, "add", "src/marker.py")
    git(project, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
        "-c", "core.hooksPath=/dev/null", "commit", "-qm", "source")
    linked = project / ".worktrees/ticket-003--fixture"
    git(project, "worktree", "add", "-qb", "ticket/003-fixture", str(linked))
    (linked / "src/marker.py").write_text("value = 'candidate'\n")
    assert execute(linked, ["python", "-c", "import marker; assert marker.value == 'candidate'"],
                   allow_primary=True) == 0
    report, = receipts(linked)
    assert report["source_binding"] == "dirty_worktree_not_attested"
