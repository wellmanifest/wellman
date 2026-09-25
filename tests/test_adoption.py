"""Required standards are independent of the implementation language."""
import json
from pathlib import Path

import pytest

from wellman.adoption import register, expand_profiles, SCHEMA
from wellman.cli import main
from wellman.registry import PROFILES_CATALOG, Profile


@pytest.mark.parametrize('marker', [None, 'README.md', 'pyproject.toml', 'package.json',
    'go.mod', 'Cargo.toml', 'pom.xml', 'build.gradle', 'CMakeLists.txt', 'App.csproj', 'unknown.xyz'])
def test_baseline_for_every_language_and_unknown_project(tmp_path, marker):
    if marker:
        (tmp_path / marker).touch()
    result = register(tmp_path)
    assert {item['id'] for item in result['registration']['requirements']} == set(expand_profiles(['baseline']))
    assert result['conformance'] == 'unverified'
    assert not (tmp_path / '.governance' / 'manifest.json').exists()


def test_polyglot_deployment_and_profile_inheritance(tmp_path):
    for marker in ['pyproject.toml', 'package.json', 'Dockerfile']:
        (tmp_path / marker).touch()
    result = register(tmp_path, ['agent-executor'])
    levels = {r['id']: r['minimumLevel'] for r in result['registration']['requirements']}
    assert levels['wellmanifest/logs'] == 'S5'
    assert levels['wellmanifest/merge'] == 'S5'
    assert 'wellmanifest/repair-lifecycle' in levels
    assert 'wellmanifest/worktrees' in levels


def test_preserves_manifests_and_idempotent_bytes(tmp_path):
    folder = tmp_path / '.governance'
    folder.mkdir()
    adoption = {'profile': 'runtime-service', 'adoptions': [{'id': 'custom', 'revision': 'pinned'}]}
    (folder / 'standard-adoption.json').write_text(json.dumps(adoption))
    (folder / 'manifest.json').write_text('{"custom":true}')
    original = {path.name: path.read_bytes() for path in folder.iterdir()}
    first = register(tmp_path)
    path = Path(first['path'])
    data, modified = path.read_bytes(), path.stat().st_mtime_ns
    second = register(tmp_path)
    assert second['changed'] is False
    assert path.read_bytes() == data and path.stat().st_mtime_ns == modified
    assert all((folder / name).read_bytes() == value for name, value in original.items())


def test_preserves_manual_requirements_and_metadata(tmp_path):
    folder = tmp_path / '.governance'
    folder.mkdir()
    path = folder / 'standard-requirements.json'
    path.write_text(json.dumps({'schema': SCHEMA, 'custom': 7, 'requirements': [
        {'id': 'wellmanifest/worktrees', 'minimumLevel': 'S5', 'revision': 'keep'},
        {'id': 'company/custom', 'minimumLevel': 'S2', 'note': 'keep'}]}))
    result = register(tmp_path)['registration']
    assert result['custom'] == 7
    items = {item['id']: item for item in result['requirements']}
    assert items['wellmanifest/worktrees']['minimumLevel'] == 'S5'
    assert items['wellmanifest/worktrees']['revision'] == 'keep'
    assert items['company/custom']['note'] == 'keep'


def test_preview_and_invalid_profiles_do_not_write(tmp_path):
    register(tmp_path, dry_run=True)
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError, match='Unknown profile'):
        register(tmp_path, ['made-up'])
    assert list(tmp_path.iterdir()) == []


def test_cycle_rejected(monkeypatch):
    monkeypatch.setitem(PROFILES_CATALOG, 'cycle', Profile('cycle', 'test', extends=['cycle']))
    with pytest.raises(ValueError, match='cycle'):
        expand_profiles(['cycle'])


@pytest.mark.parametrize('value', ['null', '[]', '{', '{"schema":"unknown"}',
    json.dumps({'schema': SCHEMA, 'requirements': None}),
    json.dumps({'schema': SCHEMA, 'requirements': [{'id': 'x', 'minimumLevel': []}]}),
    json.dumps({'schema': SCHEMA, 'requirements': [{'id': 'x', 'minimumLevel': 'S9'}]})])
def test_invalid_existing_registration_preserved(tmp_path, value):
    folder = tmp_path / '.governance'
    folder.mkdir()
    path = folder / 'standard-requirements.json'
    path.write_text(value)
    with pytest.raises(ValueError):
        register(tmp_path)
    assert path.read_text() == value


def test_symlink_rejected(tmp_path):
    target = tmp_path / 'target'
    target.mkdir()
    (tmp_path / '.governance').symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        register(tmp_path)
    assert list(target.iterdir()) == []


def test_existing_writer_lock_not_removed(tmp_path):
    folder = tmp_path / '.governance'
    folder.mkdir()
    lock = folder / '.standard-requirements.lock'
    lock.touch()
    with pytest.raises(FileExistsError):
        register(tmp_path)
    assert lock.exists()
    assert not (folder / 'standard-requirements.json').exists()


def test_cli_default_auto_and_preview(tmp_path, capsys):
    assert main(['adopt', '--root', str(tmp_path), '--bootstrap', '--dry-run', '--json']) == 0
    assert json.loads(capsys.readouterr().out)['dry_run'] is True
    assert not (tmp_path / '.governance').exists()
    assert main(['adopt', '--root', str(tmp_path), '--bootstrap', '--json']) == 0
    assert json.loads(capsys.readouterr().out)['changed'] is True


def test_cli_invalid_profile_and_explicit_preview_never_write(tmp_path, capsys):
    assert main(['adopt', '--root', str(tmp_path), '--bootstrap', '--profile', 'unknown']) == 1
    assert main(['adopt', 'baseline', '--root', str(tmp_path), '--bootstrap', '--dry-run']) == 1
    assert not (tmp_path / '.governance').exists()


def test_explicit_adoption_also_registers_baseline_and_selected_standard(tmp_path):
    assert main(['adopt', 'wellmanifest/anonym', '--root', str(tmp_path), '--bootstrap']) == 0
    result = json.loads((tmp_path / '.governance' / 'standard-requirements.json').read_text())
    ids = {item['id'] for item in result['requirements']}
    assert 'wellmanifest/anonym' in ids
    assert set(expand_profiles(['baseline'])) <= ids


def test_declared_role_and_domain_contract_add_profiles(tmp_path):
    folder = tmp_path / '.governance'
    folder.mkdir()
    (folder / 'manifest.json').write_text('{"repositoryRole":"agent-executor"}')
    (tmp_path / 'operations').mkdir()
    (tmp_path / 'operations' / 'index.json').write_text('{}')
    result = register(tmp_path)['registration']
    assert set(result['profiles']) == {'baseline', 'agent-executor', 'domain-pack'}


def test_file_symlink_is_preserved(tmp_path):
    folder = tmp_path / '.governance'
    folder.mkdir()
    target = tmp_path / 'external.json'
    target.write_text('{}')
    (folder / 'standard-requirements.json').symlink_to(target)
    with pytest.raises(ValueError, match='symlink'):
        register(tmp_path)
    assert target.read_text() == '{}'


def test_concurrent_change_is_not_overwritten(tmp_path, monkeypatch):
    register(tmp_path)
    path = tmp_path / '.governance' / 'standard-requirements.json'
    original = Path.read_bytes
    reads = []

    def raced(p):
        if p == path:
            reads.append(p)
            if len(reads) == 2:
                p.write_text('{"otherWriter": true}')
        return original(p)

    monkeypatch.setattr(Path, 'read_bytes', raced)
    with pytest.raises(ValueError, match='concurrently'):
        register(tmp_path, ['deployment'])
    assert json.loads(path.read_text()) == {'otherWriter': True}
    assert not (path.parent / '.standard-requirements.lock').exists()


def test_registration_api_rejects_symlink_ancestor(tmp_path):
    real = tmp_path / 'real'
    real.mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        register(alias)
    assert not (real / '.governance').exists()


def test_adopt_writes_unrestricted_local_ci_default_once(tmp_path):
    policy = tmp_path / '.governance' / 'local-ci-publication.json'
    preview = register(tmp_path, dry_run=True)
    assert preview['localCiPublication']['changed'] and not policy.exists()
    first = register(tmp_path)
    assert first['localCiPublication']['changed']
    assert json.loads(policy.read_text()) == {
        'schema': 'new-project.local-ci-publication/v1', 'scope': {'mode': 'all'}}
    again = register(tmp_path)
    assert not again['changed'] and not again['localCiPublication']['changed']


def test_adopt_keeps_an_existing_local_ci_restriction(tmp_path):
    (tmp_path / '.governance').mkdir()
    policy = tmp_path / '.governance' / 'local-ci-publication.json'
    restricted = {'schema': 'new-project.local-ci-publication/v1',
                  'scope': {'mode': 'restricted', 'repositories': ['maskservice/*']}}
    policy.write_text(json.dumps(restricted))
    result = register(tmp_path)
    assert not result['localCiPublication']['changed']
    assert json.loads(policy.read_text()) == restricted
