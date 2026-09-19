"""Tests for Wellman CLI commands."""

import json
from wellman.cli import main


def test_cli_version(capsys):
    ret = main(["--version"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "wellman" in captured.out


def test_cli_standards(capsys):
    ret = main(["standards"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "wellmanifest/git-lifecycle" in captured.out
    assert "wellmanifest/worktrees" in captured.out


def test_cli_standards_json(capsys):
    ret = main(["standards", "--json"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert isinstance(data, list)
    assert any(s["id"] == "wellmanifest/git-lifecycle" for s in data)


def test_cli_info(capsys):
    ret = main(["info", "wellmanifest/new-project"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "New Project" in captured.out
    assert "Owned Concerns:" in captured.out


def test_cli_info_unknown(capsys):
    ret = main(["info", "nonexistent/standard"])
    assert ret == 1
    captured = capsys.readouterr()
    assert "Unknown standard" in captured.err


def test_cli_profiles(capsys):
    ret = main(["profiles"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Profile: baseline" in captured.out


def test_cli_profiles_json(capsys):
    ret = main(["profiles", "--json"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert isinstance(data, list)
    assert any(p["name"] == "baseline" for p in data)
