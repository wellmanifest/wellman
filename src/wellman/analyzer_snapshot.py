"""Pinned static analysis of copied inputs, with atomic complete snapshots.

Run ``python -m wellman.analyzer_snapshot ROOT --output STORE --python PYTHON``.
Prepare the separately pinned analyzer environment before scanning. This module
never installs packages, adopts standards, imports product code or grants trust.
Process receipts establish local provenance, not independent conformance.
Analyzer package bytes are observed; transitive dependencies retain version
metadata only. Before/after observations are not an immutable execution sandbox.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from wellman.components import _safe
from wellman.evidence import CONTRACTS, _json, _shape, normalize_report
from wellman.selection_contracts import (
    MAX_DOCUMENT_BYTES,
    ContractError,
    canonical_bytes,
    payload_digest,
    validate_document,
)
from wellman.selection_plan import _identity, capture_repository

VERSION = 'wellman.analyzer-snapshot/v1'
# All tools receive the same explicit Python input projection, without project
# configuration, Git hooks, credentials, generated code or historical copies.
EXCLUSIONS = tuple(p for name in (
    '.worktrees', '.subactor', '.codex', 'node_modules', 'venv', '.venv',
    '.venv-test', 'build', 'dist', 'generated', 'vendor', 'vendored',
    'gitive-isolated', 'work', 'results', '.code2llm_cache', '.playwright-browsers',
) for p in (name + '/**', '**/' + name + '/**')) + ('**/src/gen/schemas/**', '**/gen/schemas/**')


def _stamp():
    return datetime.now(timezone.utc).isoformat()


def _safe_root(value):
    path = Path(value).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ContractError('Snapshot paths must not traverse symlinks')
    return path


def _write(path, data):
    raw = canonical_bytes(data)
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ContractError('Snapshot document exceeds byte budget')
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _run(argv, cwd, log, timeout):
    """Wait for each process; kill its process group on timeout, without shell."""
    result = {'started_at': _stamp(), 'exit_code': None, 'timeout': False}
    with log.open('xb') as output:
        try:
            process = subprocess.Popen(
                argv, cwd=cwd, stdout=output, stderr=subprocess.STDOUT,
                start_new_session=True,
                env={k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')},
            )
            try:
                result['exit_code'] = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                result['timeout'] = True
                os.killpg(process.pid, signal.SIGKILL)
                result['exit_code'] = process.wait()
        except OSError as error:
            result['error'] = type(error).__name__
            result['exit_code'] = 127
    result.update(finished_at=_stamp(), log_truncated=log.stat().st_size > MAX_DOCUMENT_BYTES)
    if result['log_truncated']:
        with log.open('r+b') as stream:
            stream.truncate(MAX_DOCUMENT_BYTES)
    return result


# Executed by the pinned interpreter using only its standard library. Resolve
# top-level packages without importing analyzers, including files absent from
# distribution RECORD. Bound traversal and reads across the entire observation.
_ENVIRONMENT_SCRIPT = r'''
import hashlib, importlib.metadata as m, importlib.machinery as machinery
import json, os, stat, sys
from pathlib import Path

versions, implementations = {}, {}
entries_seen = bytes_seen = 0
for name in json.loads(sys.argv[1]):
    try:
        versions[name] = m.version(name)
    except m.PackageNotFoundError:
        versions[name] = implementations[name] = None
        continue
    spec = machinery.PathFinder.find_spec(name, sys.path)
    locations = list(spec.submodule_search_locations or []) if spec else []
    if len(locations) != 1:
        raise ValueError('Analyzer package root unavailable or ambiguous')
    root = Path(locations[0]).absolute()
    if not root.is_dir() or any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError('Unsafe analyzer package root')
    files = []
    def walk_error(error):
        raise error
    for directory, directories, names in os.walk(root, followlinks=False, onerror=walk_error):
        entries_seen += len(directories) + len(names)
        if entries_seen > 5000:
            raise ValueError('Analyzer package entry budget exceeded')
        for child in directories:
            if (Path(directory) / child).is_symlink():
                raise ValueError('Analyzer package directory symlink')
        # Commands use a fresh pycache_prefix and -B, so installed caches are
        # neither read nor written. Legacy .pyc outside __pycache__ stays bound.
        directories[:] = sorted(d for d in directories if d != '__pycache__')
        for filename in sorted(names):
            path = Path(directory) / filename
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, 'rb') as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise ValueError('Nonregular analyzer package file')
                if bytes_seen + before.st_size > 128 * 1024 * 1024:
                    raise ValueError('Analyzer package byte budget exceeded')
                digest, size = hashlib.sha256(), 0
                while True:
                    chunk = stream.read(65536)
                    if not chunk:
                        break
                    bytes_seen += len(chunk)
                    size += len(chunk)
                    if bytes_seen > 128 * 1024 * 1024:
                        raise ValueError('Analyzer package byte budget exceeded')
                    digest.update(chunk)
                after = os.fstat(stream.fileno())
                identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
                if identity(before) != identity(after) or size != before.st_size:
                    raise ValueError('Analyzer package changed while observed')
            files.append({'path': path.relative_to(root).as_posix(),
                          'size_bytes': size, 'sha256': digest.hexdigest()})
    files.sort(key=lambda f: f['path'])
    implementations[name] = {
        'root': str(root), 'files': files,
        'digest': hashlib.sha256(json.dumps(files, sort_keys=True,
                    separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()}
print(json.dumps({'versions': versions, 'implementations': implementations,
    'implementation_scope': 'analyzer-package-files; transitive dependency versions only',
    'python': sys.version,
    'packages': sorted((d.metadata['Name'], d.version) for d in m.distributions())}))
'''


def _environment(python, directory, timeout):
    log = directory / 'environment.json'
    outcome = _run([str(python), '-I', '-B', '-X', 'pycache_prefix='+str(directory / 'bytecode'),
                    '-c', _ENVIRONMENT_SCRIPT, json.dumps(tuple(CONTRACTS))], directory, log, timeout)
    if outcome['exit_code'] or outcome['log_truncated']:
        raise ContractError('Pinned analyzer environment unavailable')
    data = _json(log.read_bytes())
    if set(data.get('versions', {})) != set(CONTRACTS) or set(data.get('implementations', {})) != set(CONTRACTS):
        raise ContractError('Invalid analyzer version observation')
    return data


def _command(python, tool, source, directory):
    interpreter = [str(python), '-I', '-B', '-X', 'pycache_prefix='+str(directory / 'bytecode')]
    prefix = interpreter + ['-m', tool]
    if tool == 'code2llm':
        return prefix + [str(source), '-f', 'json', '-o', str(directory), '--no-cache', '--no-chunk'], directory / 'analysis.json'
    if tool == 'redup':
        return prefix + ['scan', str(source), '--format', 'json', '--output', str(directory / 'report.json'), '--no-semantic'], directory / 'report.json'
    return interpreter + ['-c', 'from prefact.cli import main; main()'] + ['scan', '--path', str(source), '--format', 'json', '--output', str(directory / 'report.json')], directory / 'report.json'


def _copy_source(root, source, files):
    source.mkdir()
    for entry in files:
        original = _safe(root, entry['path'])
        raw = original.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry['sha256']:
            raise ContractError('Source changed while preparing analyzer inputs')
        target = source / entry['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return _projection_digest(source)


def _projection_digest(source):
    _safe_root(source)
    entries = []
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            raise ContractError('Analyzer input became a symlink')
        if path.is_file():
            entries.append({'path': path.relative_to(source).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    return payload_digest(entries)


def _stage(tool, python, directory, inventory, files, root, environment, observation_id, timeout):
    directory.mkdir()
    source = directory / 'input'
    projection = _copy_source(root, source, files)
    argv, report = _command(python, tool, source, directory)
    configuration = {'version': VERSION, 'tool': tool, 'command': argv[2:],
                     'input_digest': projection, 'exclusions': inventory['exclusions'], 'language_scope': ['python']}
    outcome = _run(argv, directory, directory / 'process.log', timeout)
    receipt = dict(outcome, tool=tool, version=environment['versions'].get(tool),
                   output_schema=CONTRACTS[tool][1], observation_id=observation_id,
                   source_digest=inventory['source_digest'], local_changes_digest=inventory['local_changes_digest'],
                   head=inventory['head'], scope_digest=inventory['scope_digest'],
                   configuration_digest=payload_digest(configuration), environment_digest=payload_digest(environment),
                   effective_exclusions=inventory['exclusions'], input_root=str(source), input_digest=projection,
                   coverage='complete', truncated=False)
    errors = []
    try:
        if _projection_digest(source) != projection:
            errors.append('ANALYZER_CHANGED_INPUT')
        if report.exists():
            if report.is_symlink() or not report.is_file() or report.stat().st_size > MAX_DOCUMENT_BYTES:
                raise ContractError('Unsafe or oversized analyzer report')
            raw = report.read_bytes()
            data = _json(raw)
            if not _shape(tool, data):
                raise ContractError('Analyzer report shape mismatch')
            receipt['sha256'] = hashlib.sha256(raw).hexdigest()
            if tool == 'code2llm' and all(k in data for k in ('nodes', 'edges', 'entry_points')):
                receipt['graph_scope'] = 'complete'
            if tool == 'code2llm':
                actual = {Path(m['file']).relative_to(source).as_posix()
                          if Path(m['file']).is_absolute() else m['file']
                          for m in data.get('modules', {}).values() if isinstance(m, dict) and isinstance(m.get('file'), str)}
                if actual != {f['path'] for f in files}:
                    errors.append('ANALYZER_COVERAGE_PARTIAL')
        if outcome['log_truncated']:
            errors.append('PROCESS_LOG_TRUNCATED')
    except (OSError, ValueError, ContractError):
        errors.append('REPORT_INVALID')
    if errors:
        receipt.update(coverage='partial', truncated=True)
    normalized = normalize_report(tool, directory.parent, report.relative_to(directory.parent).as_posix(),
                                  inventory, version=receipt['version'], output_schema=receipt['output_schema'],
                                  receipt=receipt, outcome=outcome, source_root=source)
    if errors and outcome['exit_code'] == 0 and not outcome['timeout']:
        normalized['stage'].update(status='partial', coverage='partial', truncated=True)
        normalized['stage']['errors'].extend(errors)
    _write(directory / 'receipt.json', {'schema': VERSION, 'grants_authority': False,
                                        'configuration': configuration, 'process': outcome, 'receipt': receipt})
    # The temporary input is not a report artifact and is discarded only after
    # mutation checks. Failures retain their reports and separate process facts.
    shutil.rmtree(source)
    return normalized


def _publish(attempt, store, record):
    import fcntl

    descriptor = os.open(store / '.publication.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _safe_root(store / 'current.json')
        if _json((attempt / 'manifest.json').read_bytes()) != record:
            raise ContractError('Snapshot manifest changed before publication')
        paths = set()
        for path in attempt.rglob('*'):
            if path.is_symlink():
                raise ContractError('Symlink artifact before publication')
            if path.is_file():
                paths.add(path.relative_to(attempt).as_posix())
        if paths != {e['path'] for e in record['artifacts']} | {'manifest.json'}:
            raise ContractError('Artifact set changed before snapshot publication')
        for entry in record['artifacts']:
            path = _safe(attempt, entry['path'])
            if not path.is_file() or path.stat().st_size != entry['size_bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
                raise ContractError('Artifact changed before snapshot publication')
        snapshots = _safe_root(store / 'snapshots')
        snapshots.mkdir(exist_ok=True)
        target = snapshots / attempt.name
        attempt.rename(target)
        pointer = {'schema': VERSION, 'grants_authority': False,
                   'snapshot': target.relative_to(store).as_posix(),
                   'manifest_sha256': hashlib.sha256((target / 'manifest.json').read_bytes()).hexdigest(),
                   'observation_id': record['observation_id'], 'complete': True}
        temporary = store / ('.current-' + uuid.uuid4().hex + '.json')
        try:
            _write(temporary, pointer)
            os.replace(temporary, store / 'current.json')
        finally:
            if temporary.exists():
                temporary.unlink()
        return pointer


def scan_repository(root, store, *, python, exclusions=(), timeout=120):
    """Collect a Python-scoped observation; incomplete attempts never go current.

    All stages run against separate identical projections. Analyzer installations
    are external prerequisites, not scan actions. A complete local snapshot is
    evidence input for recommendations, never permission to install standards.
    """
    if os.name != 'posix':
        raise ContractError('Analyzer process isolation requires POSIX')
    root, store, python = _safe_root(root), _safe_root(store), Path(python).absolute()
    if root == store or root in store.parents or store in root.parents:
        raise ContractError('Snapshot store must be separate from source repository')
    if type(timeout) not in (int, float) or not 0 < timeout <= 300:
        raise ContractError('Invalid analyzer timeout')
    _safe_root(store / 'snapshots')
    _safe_root(store / '.publication.lock')
    store.mkdir(parents=True, exist_ok=True)
    attempts = store / 'attempts'
    _safe_root(attempts)
    attempts.mkdir(exist_ok=True)
    attempt = Path(tempfile.mkdtemp(prefix='scan-', dir=attempts))
    oid = 'observation:' + attempt.name
    record = {'schema': VERSION, 'observation_id': oid, 'grants_authority': False,
              'started_at': _stamp(), 'complete': False, 'published': False, 'errors': [], 'stages': []}
    try:
        captured = capture_repository(root, exclusions=(*EXCLUSIONS, *exclusions), observation_id=oid)
        inventory, observation = captured['inventory'], captured['observation']
        record['source'] = _identity(inventory)
        if not inventory['complete'] or inventory['identity'] != 'confirmed':
            raise ContractError('Confirmed complete Git inventory required')
        files = [f for f in inventory['files'] if f.get('sha256') and f['path'].endswith('.py')
                 and f['class'] == 'first_party']
        record['language_scope'] = ['python']
        record['input_files'] = [{'path': f['path'], 'sha256': f['sha256']} for f in files]
        if not files:
            raise ContractError('No confirmed first-party Python input files')
        before_environment = attempt / 'environment-before'
        before_environment.mkdir()
        environment = _environment(python, before_environment, min(timeout, 30))
        _write(attempt / 'inventory.json', inventory)
        _write(attempt / 'adoption.json', captured['adoptions'][inventory['repository_id']])
        for tool, (version, _) in CONTRACTS.items():
            if environment['versions'][tool] != version:
                result = {'id': tool, 'status': 'unsupported', 'expected_version': version,
                          'observed_version': environment['versions'][tool], 'errors': ['TOOL_VERSION_MISMATCH']}
                record['stages'].append(result)
                continue
            normalized = _stage(tool, python, attempt / tool, inventory, files, root, environment, oid, timeout)
            record['stages'].append(normalized['stage'])
            observation['tools'].append(normalized['tool'])
            observation['stages'].append(normalized['stage'])
            observation['artifacts'].extend(normalized['artifacts'])
            observation['features'].extend(normalized['features'])
            observation['metrics'].extend(normalized['metrics'])
            observation['quality_issues'].extend(normalized['quality_issues'])
        after_environment = attempt / 'environment-after'
        after_environment.mkdir()
        if _environment(python, after_environment, min(timeout, 30)) != environment:
            raise ContractError('ANALYZER_ENVIRONMENT_CHANGED_DURING_SCAN')
        after = capture_repository(root, exclusions=(*EXCLUSIONS, *exclusions), observation_id=oid)
        if _identity(after['inventory']) != _identity(inventory) or after['adoptions'] != captured['adoptions']:
            raise ContractError('SOURCE_CHANGED_DURING_SCAN')
        observation['finished_at'] = _stamp()
        validate_document(observation)
        _write(attempt / 'observation.json', observation)
        record['complete'] = all(s['status'] == 'complete' and not s.get('truncated') for s in record['stages'])
    except (OSError, ValueError, ContractError, subprocess.SubprocessError) as error:
        record['errors'].append(str(error))
    record['finished_at'] = _stamp()
    # Hash every retained regular artifact, including process/config receipts.
    artifacts = []
    for path in sorted(attempt.rglob('*')):
        if path.is_symlink():
            record['errors'].append('SYMLINK_ARTIFACT')
            record['complete'] = False
        elif path.is_file():
            artifacts.append({'path': path.relative_to(attempt).as_posix(),
                              'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'size_bytes': path.stat().st_size})
    record['artifacts'] = artifacts
    _write(attempt / 'manifest.json', record)
    if record['complete'] and not record['errors']:
        pointer = _publish(attempt, store, record)
        return dict(record, published=True, pointer=pointer)
    return dict(record, attempt=attempt.relative_to(store).as_posix())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root')
    parser.add_argument('--output', required=True)
    parser.add_argument('--python', required=True, help='Python in a separately prepared pinned analyzer environment')
    parser.add_argument('--exclude', action='append', default=[])
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args(argv)
    result = scan_repository(args.root, args.output, python=args.python, exclusions=args.exclude, timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['published'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
