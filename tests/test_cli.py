"""Tests for Wellman CLI commands."""

import json
import subprocess

import pytest

from wellman import __version__
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


def test_cli_check_rejects_unknown_standard(capsys, tmp_path):
    ret = main(["check", "--root", str(tmp_path), "--standard", "wellmanifest/nope", "--json"])

    assert ret == 1
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] is False
    assert result["findings"][0]["code"] == "GOV-STANDARD-UNKNOWN"


def test_cli_check_fails_closed_for_unimplemented_standard(capsys, tmp_path):
    ret = main(["check", "--root", str(tmp_path), "--standard", "wellmanifest/docs", "--json"])

    assert ret == 1
    result = json.loads(capsys.readouterr().out)
    assert result["findings"][0]["code"] == "GOV-DOCS-MISSING"


def test_cli_check_rejects_git_checkout_below_system_tmp(capsys, tmp_path):
    git(tmp_path, "init", "-q")

    ret = main([
        "check", "--root", str(tmp_path),
        "--standard", "wellmanifest/worktrees", "--json",
    ])

    assert ret == 1
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] is False
    assert result["findings"][0]["code"] == "GOV-WORKTREE-ADMISSION-001"


def test_cli_adopt_rejects_unknown_target_without_writing(capsys, tmp_path):
    ret = main(["adopt", "wellmanifest/nope", "--root", str(tmp_path), "--bootstrap"])

    assert ret == 1
    assert not (tmp_path / ".governance").exists()
    assert "Unknown standard or profile" in capsys.readouterr().err


def test_cli_adopt_does_not_overwrite_manifest_without_force(capsys, tmp_path):
    manifest = tmp_path / ".governance" / "manifest.json"
    manifest.parent.mkdir()
    manifest.write_text('{"preserve": true}\n', encoding="utf-8")

    ret = main(["adopt", "baseline", "--root", str(tmp_path), "--bootstrap"])

    assert ret == 1
    assert manifest.read_text(encoding="utf-8") == '{"preserve": true}\n'
    assert "without --force" in capsys.readouterr().err

    ret = main([
        "adopt", "baseline", "--root", str(tmp_path), "--force", "--bootstrap",
        "--repository", "acme/example",
    ])

    assert ret == 0
    adopted = json.loads(manifest.read_text(encoding="utf-8"))
    assert adopted["standard"]["id"] == "profile:baseline"


def test_cli_adopt_uses_running_package_version(capsys, tmp_path):
    ret = main([
        "adopt", "baseline", "--root", str(tmp_path), "--bootstrap",
        "--repository", "acme/example",
    ])

    assert ret == 0
    manifest = json.loads((tmp_path / ".governance" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["standard"] == {"id": "profile:baseline", "version": __version__}
    assert "Adoption scaffolded" in capsys.readouterr().out


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.mark.parametrize('target', ['auto', 'baseline'])
def test_adopt_requires_explicit_non_git_bootstrap(tmp_path, capsys, target):
    assert main(['adopt', target, '--root', str(tmp_path)]) == 1
    assert '--bootstrap' in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []
    assert main([
        'adopt', target, '--root', str(tmp_path), '--bootstrap',
        '--repository', 'acme/example',
    ]) == 0
    assert (tmp_path / '.governance' / 'standard-requirements.json').is_file()


@pytest.mark.parametrize('explicit_root', [True, False])
@pytest.mark.parametrize('bootstrap', [True, False])
def test_adopt_from_nested_directory_uses_git_root(tmp_path, monkeypatch, capsys, explicit_root, bootstrap):
    git(tmp_path, 'init', '-q')
    nested = tmp_path / 'src' / 'deep'
    nested.mkdir(parents=True)
    argv = ['adopt', '--json']
    if bootstrap:
        argv.append('--bootstrap')
    if explicit_root:
        argv += ['--root', str(nested)]
    else:
        monkeypatch.chdir(nested)
    argv += ['--repository', 'acme/example']
    assert main(argv) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['path'] == str(tmp_path / '.governance' / 'standard-requirements.json')
    assert not (nested / '.governance').exists()


def test_adopt_linked_worktree_does_not_write_primary(tmp_path, capsys):
    primary, linked = tmp_path / 'primary', tmp_path / 'linked'
    primary.mkdir()
    git(primary, 'init', '-q')
    git(primary, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
        'commit', '--allow-empty', '-qm', 'fixture')
    git(primary, 'worktree', 'add', '--detach', str(linked), 'HEAD')
    nested = linked / 'nested'
    nested.mkdir()
    assert main(['adopt', '--root', str(nested), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['path'].startswith(str(linked) + '/')
    assert not (primary / '.governance').exists()
    assert not (nested / '.governance').exists()


@pytest.mark.parametrize('target', ['auto', 'baseline'])
@pytest.mark.parametrize('link_name', ['.governance', '.governance/manifest.json',
                                     '.governance/standard-packs.json',
                                     '.governance/standard-requirements.json'])
def test_adopt_rejects_symlink_targets_before_any_write(tmp_path, capsys, target, link_name):
    repository = tmp_path / 'repository'
    repository.mkdir()
    outside = tmp_path / 'outside'
    link = repository / link_name
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside, target_is_directory=link_name == '.governance')
    assert main(['adopt', target, '--root', str(repository), '--bootstrap', '--force']) == 1
    assert 'symlink' in capsys.readouterr().err
    assert link.is_symlink()
    assert not outside.exists()
    assert not (repository / '.governance' / 'standard-requirements.json').is_file()


def test_adopt_rejects_symlink_ancestor_and_symlink_dotdot(tmp_path, capsys):
    real = tmp_path / 'real'
    real.mkdir()
    (real / 'nested').mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(real, target_is_directory=True)
    for target in (alias / 'nested', alias / '..' / 'real'):
        assert main(['adopt', '--root', str(target), '--bootstrap']) == 1
        assert 'symlink' in capsys.readouterr().err
    assert not (real / '.governance').exists()


def test_adopt_ignores_inherited_git_location_overrides(tmp_path, monkeypatch):
    own, other = tmp_path / 'own', tmp_path / 'other'
    own.mkdir()
    other.mkdir()
    git(own, 'init', '-q')
    git(other, 'init', '-q')
    monkeypatch.setenv('GIT_DIR', str(other / '.git'))
    monkeypatch.setenv('GIT_WORK_TREE', str(other))
    assert main(['adopt', '--root', str(own), '--repository', 'acme/own']) == 0
    assert (own / '.governance' / 'standard-requirements.json').exists()
    assert not (other / '.governance').exists()


def test_bootstrap_does_not_hide_broken_or_bare_git_metadata(tmp_path):
    broken, bare = tmp_path / 'broken', tmp_path / 'bare'
    broken.mkdir()
    (broken / '.git').write_text('gitdir: missing\n')
    bare.mkdir()
    git(bare, 'init', '--bare', '-q')
    for root in (broken, bare):
        assert main(['adopt', '--root', str(root), '--bootstrap']) == 1
        assert not (root / '.governance').exists()
