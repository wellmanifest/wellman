import hashlib
import json
import os
import py_compile
import subprocess
import sys
import venv

import pytest

from wellman import analyzer_snapshot as scan
from wellman.selection_contracts import (
    ContractError,
    validate_document,
)

REAL_ENVIRONMENT = scan._environment


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True, check=True)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    git(root, 'init', '-b', 'main')
    git(root, 'config', 'user.email', 'test@example.invalid')
    git(root, 'config', 'user.name', 'Fixture')
    git(root, 'remote', 'add', 'origin', 'https://github.com/example/scanner.git')
    (root / 'package.json').write_text('{"name":"fixture","source":"src/main.py"}')
    (root / 'src').mkdir()
    (root / 'src/main.py').write_text('value = 1\n')
    (root / 'src/generated').mkdir()
    (root / 'src/generated/no.py').write_text('raise RuntimeError("must not run")\n')
    (root / 'src/gen/schemas').mkdir(parents=True)
    (root / 'src/gen/schemas/no.py').write_text('raise RuntimeError("must not run")\n')
    (root / '.env').write_text('private fixture data\n')
    (root / '.gitignore').write_text('.env\n')
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'Fixture')
    return root


@pytest.fixture
def tools(monkeypatch):
    environment = {'versions': {n: v[0] for n, v in scan.CONTRACTS.items()}, 'python': sys.version}
    monkeypatch.setattr(scan, '_environment', lambda *args: environment)
    modes = {}
    calls = []

    def command(python, tool, source, directory):
        calls.append((tool, sorted(p.relative_to(source).as_posix() for p in source.rglob('*.py'))))
        report = directory / 'report.json'
        mode = modes.get(tool)
        data = {
            'code2llm': {'project_path': str(source), 'modules': {'main': {'file': str(source / 'src/main.py'), 'imports': []}},
                         'nodes': {'main': {'file': str(source / 'src/main.py')}}, 'edges': [], 'entry_points': []},
            'redup': {'stats': {}, 'summary': {'total_groups': 0}, 'groups': []},
            'prefact': {'dry_run': True, 'summary': {'issues': 0}, 'issues': [], 'fixes': [], 'validations': []},
        }[tool]
        if mode == 'partial':
            data = {'stats': {}, 'summary': {'total_groups': 2}, 'groups': []}
        script = 'from pathlib import Path; import time; '
        if mode == 'timeout':
            script += 'time.sleep(20); '
        if mode == 'mutate':
            script += 'Path('+repr(str(source / 'src/main.py'))+').write_text("changed"); '
        if mode == 'symlink':
            script += 'Path('+repr(str(report))+').symlink_to('+repr(str(source / 'src/main.py'))+'); '
        elif mode == 'invalid':
            script += 'Path('+repr(str(report))+').write_text("not json"); '
        elif mode != 'missing':
            script += 'Path('+repr(str(report))+').write_text('+repr(json.dumps(data))+'); '
        script += 'raise SystemExit('+('7' if mode == 'fail' else '0')+')'
        return [str(python), '-I', '-c', script], report

    monkeypatch.setattr(scan, '_command', command)
    return environment, modes, calls


@pytest.fixture
def installed_tools(tmp_path):
    environment = tmp_path / 'analyzer-venv'
    venv.EnvBuilder(with_pip=False).create(environment)
    python = environment / 'bin/python'
    site = subprocess.check_output(
        [str(python), '-I', '-c', 'import sysconfig; print(sysconfig.get_path("purelib"))'],
        text=True,
    ).strip()
    from pathlib import Path
    site = Path(site)
    for name, (version, _) in scan.CONTRACTS.items():
        package = site / name
        package.mkdir()
        (package / '__init__.py').write_text('raise RuntimeError("probe must not import analyzers")\n')
        distribution = site / (name + '-' + version + '.dist-info')
        distribution.mkdir()
        (distribution / 'METADATA').write_text('Metadata-Version: 2.1\nName: ' + name + '\nVersion: ' + version + '\n')
    return python, site


def test_actual_probe_binds_same_version_analyzer_code_without_importing(installed_tools, tmp_path):
    python, site = installed_tools
    before_dir, after_dir = tmp_path / 'before', tmp_path / 'after'
    before_dir.mkdir(); after_dir.mkdir()
    before = REAL_ENVIRONMENT(python, before_dir, 30)
    (site / 'code2llm/__init__.py').write_text('raise RuntimeError("different implementation, same version")\n')
    after = REAL_ENVIRONMENT(python, after_dir, 30)
    assert before['versions'] == after['versions']
    assert before['packages'] == after['packages']
    assert before != after


def test_package_cache_changes_do_not_change_observed_implementation(installed_tools, tmp_path):
    python, site = installed_tools
    before_dir, after_dir = tmp_path / 'before', tmp_path / 'after'
    before_dir.mkdir(); after_dir.mkdir()
    before = REAL_ENVIRONMENT(python, before_dir, 30)
    cache = site / 'code2llm/__pycache__'
    cache.mkdir()
    (cache / 'unused.pyc').write_bytes(b'ordinary unexecuted cache')
    assert REAL_ENVIRONMENT(python, after_dir, 30) == before


def test_probe_rejects_package_symlinks(installed_tools, tmp_path):
    python, site = installed_tools
    outside = tmp_path / 'outside.py'
    outside.write_text('unrelated data')
    (site / 'code2llm/linked.py').symlink_to(outside)
    directory = tmp_path / 'probe'; directory.mkdir()
    with pytest.raises(ContractError):
        REAL_ENVIRONMENT(python, directory, 30)


def test_probe_rejects_oversized_package_without_reading_it(installed_tools, tmp_path):
    python, site = installed_tools
    with (site / 'code2llm/oversized.bin').open('wb') as stream:
        stream.truncate(129 * 1024 * 1024)
    directory = tmp_path / 'probe'; directory.mkdir()
    with pytest.raises(ContractError):
        REAL_ENVIRONMENT(python, directory, 30)


def test_command_ignores_valid_stale_installed_bytecode(installed_tools, tmp_path):
    python, site = installed_tools
    (site / 'prefact/__init__.py').write_text('')
    module = site / 'prefact/cli.py'
    module.write_text('def main(): print("OLD")\n')
    old_stat = module.stat()
    py_compile.compile(str(module), doraise=True)
    module.write_text('def main(): print("NEW")\n')
    os.utime(module, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
    # Establish that this cache really shadows the equal-size source normally.
    assert subprocess.check_output([str(python), '-I', '-c',
        'from prefact.cli import main; main()'], text=True).strip() == 'OLD'
    directory = tmp_path / 'stage'; directory.mkdir()
    argv, _ = scan._command(python, 'prefact', tmp_path / 'input', directory)
    assert subprocess.check_output(argv, text=True).strip() == 'NEW'
    assert not (directory / 'bytecode').exists()


@pytest.mark.parametrize('tool', list(scan.CONTRACTS))
def test_analyzer_commands_use_fresh_bytecode_lookup_without_cache_writes(tool, tmp_path):
    argv, _ = scan._command(sys.executable, tool, tmp_path / 'input', tmp_path / 'stage')
    assert '-B' in argv and '-I' in argv
    assert '-X' in argv
    assert 'pycache_prefix=' + str(tmp_path / 'stage/bytecode') in argv


def test_same_version_code_drift_preserves_previous_snapshot(repo, tmp_path, tools, installed_tools, monkeypatch):
    python, site = installed_tools
    monkeypatch.setattr(scan, '_environment', REAL_ENVIRONMENT)
    store = tmp_path / 'store'
    first = scan.scan_repository(repo, store, python=python)
    assert first['published']
    pointer = (store / 'current.json').read_bytes()
    original = scan._stage

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[0] == 'prefact':
            (site / 'code2llm/__init__.py').write_text('raise RuntimeError("same-version drift")\n')
        return result

    monkeypatch.setattr(scan, '_stage', changed)
    result = scan.scan_repository(repo, store, python=python)
    assert not result['published']
    assert 'ANALYZER_ENVIRONMENT_CHANGED_DURING_SCAN' in result['errors']
    assert (store / 'current.json').read_bytes() == pointer


def run(repo, tmp_path, **kwargs):
    return scan.scan_repository(repo, tmp_path / 'store', python=sys.executable, **kwargs)


def test_complete_snapshot_has_valid_observation_and_all_artifact_hashes(repo, tmp_path, tools):
    before = (repo / 'src/main.py').read_bytes()
    result = run(repo, tmp_path)
    assert result['published'] and result['complete']
    assert result['grants_authority'] is False
    assert [s['status'] for s in result['stages']] == ['complete'] * 3
    assert tools[2] == [(n, ['src/main.py']) for n in scan.CONTRACTS]
    target = tmp_path / 'store' / result['pointer']['snapshot']
    observation = json.loads((target / 'observation.json').read_text())
    validate_document(observation)
    for item in result['artifacts']:
        assert hashlib.sha256((target / item['path']).read_bytes()).hexdigest() == item['sha256']
    assert not list(target.rglob('input'))
    assert before == (repo / 'src/main.py').read_bytes()
    assert git(repo, 'status', '--porcelain').stdout == b''


@pytest.mark.parametrize('mode,status', [('fail','failed'), ('timeout','failed'), ('missing','missing'),
                                        ('partial','partial'), ('mutate','partial'), ('invalid','partial'), ('symlink','partial')])
def test_each_failed_stage_preserves_prior_snapshot_and_does_not_mask_later_success(repo, tmp_path, tools, mode, status, monkeypatch):
    run(repo, tmp_path)
    pointer = (tmp_path / 'store/current.json').read_bytes()
    tools[1]['redup'] = mode
    original = scan._run
    if mode == 'timeout':
        monkeypatch.setattr(scan, '_run', lambda argv, cwd, log, timeout: original(argv, cwd, log, 0.1 if cwd.name == 'redup' else timeout))
    result = run(repo, tmp_path, timeout=10)
    assert result['published'] is False
    assert result['stages'][1]['status'] == status
    assert result['stages'][2]['status'] == 'complete'
    assert (tmp_path / 'store/current.json').read_bytes() == pointer
    assert (tmp_path / 'store' / result['attempt'] / 'manifest.json').exists()
    assert (repo / 'src/main.py').read_text() == 'value = 1\n'


def test_version_mismatch_is_not_silently_upgraded_or_executed(repo, tmp_path, tools):
    tools[0]['versions']['redup'] = '0.0.1'
    result = run(repo, tmp_path)
    assert not result['published']
    assert result['stages'][1]['status'] == 'unsupported'
    assert [c[0] for c in tools[2]] == ['code2llm', 'prefact']
    assert not (tmp_path / 'store/current.json').exists()


def test_source_change_during_scan_preserves_snapshot(repo, tmp_path, tools, monkeypatch):
    run(repo, tmp_path)
    pointer = (tmp_path / 'store/current.json').read_bytes()
    original = scan._stage

    def stage(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[0] == 'prefact':
            (repo / 'src/main.py').write_text('value = 2\n')
        return result

    monkeypatch.setattr(scan, '_stage', stage)
    result = run(repo, tmp_path)
    assert 'SOURCE_CHANGED_DURING_SCAN' in result['errors']
    assert (tmp_path / 'store/current.json').read_bytes() == pointer


@pytest.mark.parametrize('part', ['snapshots', 'attempts', '.publication.lock', 'current.json'])
def test_store_symlinks_are_rejected_without_touching_target(repo, tmp_path, tools, part):
    store = tmp_path / 'store'
    store.mkdir()
    outside = tmp_path / 'outside'
    outside.write_text('keep')
    (store / part).symlink_to(outside)
    with pytest.raises(ContractError, match='symlink'):
        run(repo, tmp_path)
    assert outside.read_text() == 'keep'


def test_publish_failure_preserves_previous_pointer(repo, tmp_path, tools, monkeypatch):
    run(repo, tmp_path)
    pointer = (tmp_path / 'store/current.json').read_bytes()
    monkeypatch.setattr(os, 'replace', lambda *args: (_ for _ in ()).throw(OSError('write failure')))
    with pytest.raises(OSError, match='write failure'):
        run(repo, tmp_path)
    assert (tmp_path / 'store/current.json').read_bytes() == pointer
    assert not list((tmp_path / 'store').glob('.current-*'))


def test_artifact_mutation_before_publish_is_detected(repo, tmp_path, tools, monkeypatch):
    run(repo, tmp_path)
    pointer = (tmp_path / 'store/current.json').read_bytes()
    original = scan._publish

    def publish(attempt, store, record):
        (attempt / 'redup/report.json').write_text('{}')
        return original(attempt, store, record)

    monkeypatch.setattr(scan, '_publish', publish)
    with pytest.raises(ContractError, match='Artifact changed'):
        run(repo, tmp_path)
    assert (tmp_path / 'store/current.json').read_bytes() == pointer


def test_nongit_root_remains_diagnostic_without_running_analyzers(tmp_path, tools):
    root = tmp_path / 'repo'
    root.mkdir()
    result = run(root, tmp_path)
    assert not result['published']
    assert tools[2] == []
    assert result['errors']


def test_complete_graph_and_common_scope_are_required(repo, tmp_path, tools, monkeypatch):
    original = scan._command

    def command(python, tool, source, directory):
        argv, report = original(python, tool, source, directory)
        if tool == 'code2llm':
            argv[-1] = argv[-1].replace('"nodes":', '"legacy_nodes":')
        return argv, report

    monkeypatch.setattr(scan, '_command', command)
    result = run(repo, tmp_path)
    assert result['stages'][0]['status'] == 'partial'
    assert not result['published']


def test_environment_change_blocks_publication(repo, tmp_path, tools, monkeypatch):
    run(repo, tmp_path)
    pointer = (tmp_path / 'store/current.json').read_bytes()
    environment = tools[0]
    calls = []

    def probe(*args):
        calls.append(1)
        return dict(environment, python='changed') if len(calls) == 2 else environment

    monkeypatch.setattr(scan, '_environment', probe)
    result = run(repo, tmp_path)
    assert 'ANALYZER_ENVIRONMENT_CHANGED_DURING_SCAN' in result['errors']
    assert (tmp_path / 'store/current.json').read_bytes() == pointer


def test_input_copy_refuses_stale_source_bytes(repo, tmp_path, tools, monkeypatch):
    original = scan._copy_source

    def copy(root, source, files):
        (repo / 'src/main.py').write_text('changed\n')
        return original(root, source, files)

    monkeypatch.setattr(scan, '_copy_source', copy)
    result = run(repo, tmp_path)
    assert not result['published']
    assert 'Source changed while preparing analyzer inputs' in result['errors']
    assert tools[2] == []


def test_log_truncation_is_explicit_and_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(scan, 'MAX_DOCUMENT_BYTES', 32)
    log = tmp_path / 'process.log'
    result = scan._run([sys.executable, '-I', '-c', 'print("x" * 100)'], tmp_path, log, 5)
    assert result['exit_code'] == 0
    assert result['log_truncated'] is True
    assert log.stat().st_size == 32


def test_scope_without_confirmed_python_files_does_not_run_analyzers(repo, tmp_path, tools):
    (repo / 'src/main.py').unlink()
    result = run(repo, tmp_path)
    assert not result['published']
    assert result['errors'] == ['No confirmed first-party Python input files']
    assert tools[2] == []


def test_cli_reports_nonpublication_as_failure(repo, tmp_path, tools, capsys):
    tools[1]['prefact'] = 'fail'
    status = scan.main([str(repo), '--output', str(tmp_path / 'store'), '--python', sys.executable])
    assert status == 1
    assert json.loads(capsys.readouterr().out)['published'] is False
