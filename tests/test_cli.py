"""Tests for Wellman CLI commands."""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from wellman import __version__
from wellman.cli import main
from wellman.cli import _worktree_admission


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


@pytest.mark.parametrize('target', ['baseline', 'wellmanifest/new-project', 'wellmanifest/worktrees'])
@pytest.mark.parametrize('schema', ['new-project.governance/v2', 'new-project.governance/v3'])
def test_explicit_adoption_cannot_replace_native_governance(tmp_path, capsys, target, schema):
    gov = tmp_path / '.governance'
    gov.mkdir()
    manifest = gov / 'manifest.json'
    original = json.dumps({'schema': schema, 'approvalEvidence': {'requiredBindings': ['headSha']}}).encode()
    manifest.write_bytes(original)

    assert main(['adopt', target, '--root', str(tmp_path), '--bootstrap',
                 '--force', '--repository', 'acme/example']) == 1
    assert {p.name: p.read_bytes() for p in gov.iterdir()} == {'manifest.json': original}
    assert 'pinned new-project adoption' in capsys.readouterr().err


@pytest.mark.parametrize('target', ['baseline', 'wellmanifest/new-project', 'wellmanifest/worktrees'])
@pytest.mark.parametrize('manifest_present', [False, True])
def test_explicit_adoption_preserves_locked_and_partial_adoption(tmp_path, capsys, target, manifest_present):
    gov = tmp_path / '.governance'
    gov.mkdir()
    (gov / 'manifest.lock.json').write_text('{"schema":"new-project.lock/v1"}\n')
    if manifest_present:
        (gov / 'manifest.json').write_text('{"schema":"wellmanifest.manifest/v1"}\n')
    original = {p.name: p.read_bytes() for p in gov.iterdir()}

    assert main(['adopt', target, '--root', str(tmp_path), '--bootstrap',
                 '--force', '--repository', 'acme/example']) == 1
    assert {p.name: p.read_bytes() for p in gov.iterdir()} == original
    assert 'pinned new-project adoption' in capsys.readouterr().err


def test_explicit_adoption_preserves_unreadable_manifest(tmp_path, capsys):
    gov = tmp_path / '.governance'
    gov.mkdir()
    (gov / 'manifest.json').write_bytes(b'{"schema":')
    assert main(['adopt', 'baseline', '--root', str(tmp_path), '--bootstrap',
                 '--force', '--repository', 'acme/example']) == 1
    assert {p.name: p.read_bytes() for p in gov.iterdir()} == {'manifest.json': b'{"schema":'}
    assert 'cannot inspect existing adoption' in capsys.readouterr().err


def test_auto_registration_preserves_native_governance_and_lock(tmp_path, capsys):
    gov = tmp_path / '.governance'
    gov.mkdir()
    (gov / 'manifest.json').write_text('{"schema":"new-project.governance/v2"}\n')
    (gov / 'manifest.lock.json').write_text('{"schema":"new-project.lock/v1"}\n')
    original = {p.name: p.read_bytes() for p in gov.iterdir()}
    assert main(['adopt', 'auto', '--root', str(tmp_path), '--bootstrap', '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['conformance'] == 'unverified'
    assert all((gov / name).read_bytes() == content for name, content in original.items())
    assert (gov / 'standard-requirements.json').is_file()


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.mark.parametrize(
    "directory,branch,expected_code",
    [
        (".worktrees/ticket-021--admission", "ticket/021-admission", None),
        (".worktrees/ticket-1000--admission", "ticket/1000-admission", None),
        (".worktrees/ticket-021--admission", "ticket/022-admission", "GOV-WORKTREE-ADMISSION-004"),
        (".worktrees/ticket-021--admission", "ticket/021-other", "GOV-WORKTREE-ADMISSION-004"),
        (".worktrees/ticket-021--admission", "ticket-021-admission", "GOV-WORKTREE-ADMISSION-004"),
        (".worktrees/ticket-021--admission", None, "GOV-WORKTREE-ADMISSION-004"),
        (".worktrees/nested/ticket-021--admission", "ticket/021-admission", "GOV-WORKTREE-ADMISSION-003"),
        ("legacy/ticket-021--admission", "ticket/021-admission", "GOV-WORKTREE-ADMISSION-003"),
    ],
)
def test_registered_worktree_admission_uses_canonical_v5_identity(directory, branch, expected_code):
    # Admission deliberately rejects /tmp. Keep actual Git fixtures in ignored
    # repository-local storage, then remove their entire temporary registration.
    cache = Path.cwd() / ".subactor" / "cache" / "admission-tests"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as temporary:
        primary = Path(temporary) / "primary"
        primary.mkdir()
        git(primary, "init", "-q")
        git(primary, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "--allow-empty", "-qm", "fixture")
        linked = primary / directory
        linked.parent.mkdir(parents=True, exist_ok=True)
        args = ["worktree", "add"]
        args += ["-b", branch] if branch else ["--detach"]
        git(primary, *args, str(linked), "HEAD")
        assert _worktree_admission(primary) is None
        finding = _worktree_admission(linked)
        assert (finding.code if finding else None) == expected_code


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
@pytest.mark.parametrize('link_name', ['.governance', '.governance/manifest.json', '.governance/manifest.lock.json',
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


def test_cli_adopt_auto_with_repeatable_standard_flag(tmp_path, capsys):
    ret = main([
        'adopt', 'auto', '--root', str(tmp_path), '--bootstrap',
        '--standard', 'wellmanifest/nl-dsl-llm',
        '-s', 'wellmanifest/twin-lifecycle',
        '--json',
    ])
    assert ret == 0
    result = json.loads(capsys.readouterr().out)
    req_ids = {r['id'] for r in result['registration']['requirements']}
    assert 'wellmanifest/nl-dsl-llm' in req_ids
    assert 'wellmanifest/twin-lifecycle' in req_ids


def test_cli_adopt_auto_rejects_unknown_standard_flag(tmp_path, capsys):
    ret = main([
        'adopt', 'auto', '--root', str(tmp_path), '--bootstrap',
        '--standard', 'unknown/nonexistent-standard',
    ])
    assert ret == 1
    assert 'Unknown standard' in capsys.readouterr().err


def test_cli_adopt_explicit_rejects_standard_flag(tmp_path, capsys):
    ret = main([
        'adopt', 'baseline', '--root', str(tmp_path), '--bootstrap',
        '--standard', 'wellmanifest/nl-dsl-llm',
    ])
    assert ret == 1
    assert '--standard' in capsys.readouterr().err


def test_recommend_cli_register_is_explicit_additive_and_excludes_llm(tmp_path, capsys, monkeypatch):
    import sys
    from types import SimpleNamespace
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    graph = tmp_path / 'ast.json'
    graph.write_text(json.dumps({'project_path': str(tmp_path), 'modules': {
        'tool': {'file': 'cli.py', 'imports': ['click']}}}))
    def complete(*args, **kwargs):
        return SimpleNamespace(content='{"standards":[{"id":"wellmanifest/llm","reason":"planned"}]}', provider='test', model='fixture')
    monkeypatch.setitem(sys.modules, 'subllm', SimpleNamespace(complete=complete))
    args = ['recommend', '--root', str(tmp_path), '--ast', str(graph), '--json', '--llm']
    assert main(args) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview['advice']['status'] == 'advisory'
    assert not (tmp_path / '.governance').exists()
    assert main(args + ['--register']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['registration']['changed']
    requirements = tmp_path / '.governance' / 'standard-requirements.json'
    before = requirements.read_bytes()
    assert 'wellmanifest/llm' not in [item['id'] for item in json.loads(before)['requirements']]
    assert main(args + ['--register']) == 0
    result = json.loads(capsys.readouterr().out)
    assert not result['registration']['changed'] and requirements.read_bytes() == before


def test_recommend_cli_bad_evidence_fails_before_writes(tmp_path, capsys):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    assert main(['recommend', '--root', str(tmp_path), '--evidence', 'bad', '--register']) == 1
    assert 'TOOL=JSON_PATH' in capsys.readouterr().err
    assert not (tmp_path / '.governance').exists()


def test_recommend_fleet_is_bounded_read_only_and_builds_existing_plans(tmp_path, capsys):
    for name in ['library', 'service']:
        project = tmp_path / name
        project.mkdir()
        subprocess.run(['git', 'init', '-q', str(project)], check=True)
    assert main(['recommend', '--root', str(tmp_path), '--fleet', '--plan', '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result['reports']) == 2 and not result['applied'] and not result['grantsAuthority']
    assert all(report['adoptionPlans'] for report in result['reports'])
    assert all(not (tmp_path / name / '.governance').exists() for name in ['library', 'service'])
    assert main(['recommend', '--root', str(tmp_path), '--fleet', '--max-projects', '1']) == 1
    assert 'exceeds max-projects' in capsys.readouterr().err
    assert main(['recommend', '--root', str(tmp_path), '--fleet', '--register']) == 1
    assert 'read-only' in capsys.readouterr().err
