"""Tests for Wellman CLI commands."""

import json
import subprocess

from wellman import __version__
from wellman.cli import main


def git_repository(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:acme/example.git"],
        cwd=tmp_path,
        check=True,
    )


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


def test_cli_check_rejects_unknown_standard(capsys, tmp_path):
    ret = main(["check", "--root", str(tmp_path), "--standard", "wellmanifest/nope", "--json"])

    assert ret == 1
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] is False
    assert result["findings"][0]["code"] == "GOV-STANDARD-UNKNOWN"


def test_cli_check_requires_docs_adoption(capsys, tmp_path):
    ret = main(["check", "--root", str(tmp_path), "--standard", "wellmanifest/docs", "--json"])

    assert ret == 1
    result = json.loads(capsys.readouterr().out)
    assert result["findings"][0]["code"] == "GOV-DOCS-MISSING"


def test_cli_adopt_rejects_unknown_target_without_writing(capsys, tmp_path):
    ret = main(["adopt", "wellmanifest/nope", "--root", str(tmp_path)])

    assert ret == 1
    assert not (tmp_path / ".governance").exists()
    assert "Unknown standard or profile" in capsys.readouterr().err


def test_cli_adopt_does_not_overwrite_manifest_without_force(capsys, tmp_path):
    git_repository(tmp_path)
    manifest = tmp_path / ".governance" / "manifest.json"
    manifest.parent.mkdir()
    manifest.write_text('{"preserve": true}\n', encoding="utf-8")

    ret = main(["adopt", "baseline", "--root", str(tmp_path)])

    assert ret == 1
    assert manifest.read_text(encoding="utf-8") == '{"preserve": true}\n'
    assert "without --force" in capsys.readouterr().err

    ret = main(["adopt", "baseline", "--root", str(tmp_path), "--force"])

    assert ret == 0
    adopted = json.loads(manifest.read_text(encoding="utf-8"))
    assert adopted["standard"]["id"] == "profile:baseline"


def test_cli_adopt_uses_running_package_version(capsys, tmp_path):
    git_repository(tmp_path)
    ret = main(["adopt", "baseline", "--root", str(tmp_path)])

    assert ret == 0
    manifest = json.loads((tmp_path / ".governance" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["standard"] == {"id": "profile:baseline", "version": __version__}
    docs = json.loads((tmp_path / ".governance" / "docs.json").read_text(encoding="utf-8"))
    assert docs["repository"] == "acme/example"
    assert "Adoption scaffolded" in capsys.readouterr().out


def test_cli_adopt_requires_repository_identity_before_writing(capsys, tmp_path):
    ret = main(["adopt", "baseline", "--root", str(tmp_path)])

    assert ret == 1
    assert not (tmp_path / ".governance").exists()
    assert "remote 'origin' is required" in capsys.readouterr().err


def test_cli_adopt_accepts_explicit_repository_without_origin(capsys, tmp_path):
    ret = main([
        "adopt", "wellmanifest/docs", "--root", str(tmp_path),
        "--repository", "acme/example",
    ])

    assert ret == 0
    docs = json.loads((tmp_path / ".governance" / "docs.json").read_text(encoding="utf-8"))
    assert docs["repository"] == "acme/example"


def test_cli_adopt_rejects_cross_repository_docs_before_writing(capsys, tmp_path):
    git_repository(tmp_path)
    gov_dir = tmp_path / ".governance"
    gov_dir.mkdir()
    (gov_dir / "docs.json").write_text(
        '{"schema":"wellmanifest.docs/adoption/v1","repository":"acme/other"}\n',
        encoding="utf-8",
    )

    ret = main(["adopt", "baseline", "--root", str(tmp_path)])

    assert ret == 1
    assert not (gov_dir / "manifest.json").exists()
    assert not (gov_dir / "standard-packs.json").exists()
    assert "different repository binding" in capsys.readouterr().err


def test_cli_fleet_plan_is_read_only(capsys, tmp_path):
    git_repository(tmp_path)
    ret = main(["fleet", "plan", "baseline", "--root", str(tmp_path), "--json"])

    assert ret == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ready"] == 1
    assert not (tmp_path / ".governance").exists()


def test_cli_fleet_adopt_requires_apply_for_writes(capsys, tmp_path):
    git_repository(tmp_path)
    ret = main(["fleet", "adopt", "baseline", "--root", str(tmp_path), "--json"])

    assert ret == 0
    json.loads(capsys.readouterr().out)
    assert not (tmp_path / ".governance").exists()
