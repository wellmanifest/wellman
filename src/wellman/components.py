"""Static component boundaries and file inventory; never import product code."""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import subprocess
from pathlib import Path, PurePosixPath

from wellman.repository import _normalize_remote
from wellman.selection_contracts import ContractError, payload_digest

CLASSES = {'first_party', 'generated', 'vendored', 'runtime_artifact', 'historical_copy', 'unknown'}
MANIFESTS = {'pyproject.toml', 'package.json', 'Cargo.toml'}
DEFAULT_EXCLUSIONS = ('.git/**', '.worktrees/**', '.venv/**', 'venv/**', 'node_modules/**', '__pycache__/**')
HINTS = {'work': 'historical_copy', 'vendor': 'vendored', 'vendored': 'vendored',
         'generated': 'generated', 'gen': 'generated', 'results': 'runtime_artifact'}


def _git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, timeout=10, check=False)
    if result.returncode:
        raise ContractError('Git observation unavailable')
    return result.stdout


def _safe(root, relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts or '\\' in relative:
        raise ContractError('Inventory path escapes repository')
    target = root / relative
    if any(p.is_symlink() for p in (target, *target.parents) if p == root or root in p.parents):
        raise ContractError('Symlink evidence is not read')
    return target


def _excluded(relative, patterns):
    return any(fnmatch.fnmatchcase(relative, pattern) for pattern in patterns)


def _manifest(raw, suffix):
    if suffix == '.json':
        data = json.loads(raw)
    else:
        try:
            import tomllib
        except ImportError as error:
            raise ContractError('TOML parser unavailable on this interpreter') from error
        data = tomllib.loads(raw)
    if not isinstance(data, dict):
        raise ContractError('Manifest must be an object')
    return data


def _component(repository, path, manifest, data):
    parent = PurePosixPath(path).parent.as_posix()
    roots = []
    name = data.get('name') if manifest == 'package.json' else None
    workspace = False
    members = []
    if manifest == 'Cargo.toml':
        package = data.get('package', {})
        name = package.get('name') if isinstance(package, dict) else None
        workspace = isinstance(data.get('workspace'), dict)
        members = data.get('workspace', {}).get('members', []) if workspace else []
        roots = ['src'] if name else []
    elif manifest == 'pyproject.toml':
        project = data.get('project', {})
        tool = data.get('tool', {})
        name = project.get('name') if isinstance(project, dict) else None
        if isinstance(tool, dict):
            poetry = tool.get('poetry', {})
            if not name and isinstance(poetry, dict):
                name = poetry.get('name')
            setup = tool.get('setuptools', {})
            if isinstance(setup, dict):
                mapping = setup.get('package-dir', {})
                if isinstance(mapping, dict):
                    roots += [v for v in mapping.values() if isinstance(v, str) and v not in ('', '.')]
                packages = setup.get('packages', {})
                if isinstance(packages, dict) and isinstance(packages.get('find'), dict):
                    roots += [v for v in packages['find'].get('where', []) if isinstance(v, str) and v not in ('', '.')]
    elif manifest == 'package.json':
        declared = data.get('workspaces', [])
        members = declared.get('packages', []) if isinstance(declared, dict) else declared
        workspace = bool(members)
        source = data.get('source')
        if isinstance(source, str):
            source_parent = PurePosixPath(source).parent.as_posix()
            roots = [source_parent] if source_parent != '.' else []
    if not isinstance(members, list) or any(not isinstance(m, str) for m in members):
        raise ContractError('Workspace members must be paths')
    for item in [*roots, *members]:
        if PurePosixPath(item).is_absolute() or '..' in PurePosixPath(item).parts or '\\' in item:
            raise ContractError('Manifest scope escapes repository')
    named = isinstance(name, str) and bool(name.strip())
    return {'id': repository + ':' + parent, 'repository_id': repository, 'path': parent,
            'name': name if named else None, 'kind': 'workspace' if workspace and not named else 'package',
            'boundary': 'confirmed' if named or workspace else 'unknown', 'manifests': [path],
            'evidence_refs': ['file:' + path], 'source_roots': sorted(set(roots)), 'workspace_members': members}


def inventory_repository(root, *, classification=None, exclusions=(), max_files=10000,
                         max_file_bytes=20 * 1024 * 1024):
    """Bind Git/index/worktree contents and declared package scopes without writes.

    Explicit classification policies take precedence. Directory hints alone
    remain unknown. Ignored files and secret-bearing .env files are outside the
    default scope; exclusions and every coverage gap are returned explicitly.
    """
    supplied = Path(root).absolute()
    if any(p.is_symlink() for p in (supplied, *supplied.parents)):
        raise ContractError('Repository root must not traverse symlinks')
    root = supplied.resolve()
    if (not root.is_dir() or type(max_files) is not int or max_files < 1
            or type(max_file_bytes) is not int or max_file_bytes < 1):
        raise ContractError('Invalid inventory root or bounds')
    if not isinstance(exclusions, (list, tuple)) or any(not isinstance(p, str) for p in exclusions):
        raise ContractError('Exclusions must be path patterns')
    classification = classification or {}
    if not isinstance(classification, dict) or set(classification) - CLASSES:
        raise ContractError('Unknown classification policy')
    for patterns in classification.values():
        if not isinstance(patterns, (list, tuple)) or any(not isinstance(p, str) for p in patterns):
            raise ContractError('Classification patterns must be strings')
    patterns = [*DEFAULT_EXCLUSIONS, *exclusions]
    issues = []
    try:
        if Path(os.fsdecode(_git(root, 'rev-parse', '--show-toplevel')).strip()).resolve() != root:
            raise ContractError('Inventory must start at the Git repository root')
        names = set(os.fsdecode(_git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z')).split('\0'))
        index = os.fsdecode(_git(root, 'ls-files', '--stage', '-z'))
        status = os.fsdecode(_git(root, 'status', '--porcelain=v1', '-z', '--untracked-files=all'))
        head = os.fsdecode(_git(root, 'rev-parse', 'HEAD')).strip()
        try:
            origin = os.fsdecode(_git(root, 'remote', 'get-url', 'origin')).strip()
            repository = _normalize_remote(origin)
            if repository is None:
                raise ContractError('Repository origin is not confirmed')
            identity = 'confirmed'
        except (ContractError, OSError, subprocess.TimeoutExpired):
            repository, identity = 'unconfirmed:' + root.name, 'unconfirmed'
            issues.append({'code': 'REPOSITORY_IDENTITY_UNCONFIRMED', 'path': '.'})
    except (ContractError, OSError, subprocess.TimeoutExpired):
        repository, identity, head, index, status = 'unconfirmed:' + root.name, 'unconfirmed', None, '', ''
        issues.append({'code': 'REPOSITORY_IDENTITY_UNCONFIRMED', 'path': '.'})
        names = set()
        for directory, folders, files in os.walk(root, followlinks=False):
            folders[:] = sorted(d for d in folders if d not in {'.git', '.worktrees', '.venv', 'venv', 'node_modules', '__pycache__'} and not (Path(directory)/d).is_symlink())
            for name in files:
                names.add((Path(directory)/name).relative_to(root).as_posix())
                if len(names) > max_files:
                    raise ContractError('Inventory file limit exceeded; nothing was certified')
    names.discard('')
    if len(names) > max_files:
        raise ContractError('Inventory file limit exceeded; nothing was certified')
    entries, components = [], {}
    for relative in sorted(names):
        if _excluded(relative, patterns):
            continue
        if PurePosixPath(relative).name == '.env' or PurePosixPath(relative).name.startswith('.env.') and not relative.endswith(('.example', '.sample')):
            issues.append({'code': 'SENSITIVE_FILE_EXCLUDED', 'path': relative})
            continue
        try:
            path = _safe(root, relative)
            if not path.exists():
                entries.append({'path': relative, 'kind': 'deleted', 'sha256': None, 'class': 'unknown', 'reasons': ['Tracked file removed locally']})
                continue
            before = path.stat()
            if not path.is_file() or before.st_size > max_file_bytes:
                raise ContractError('File cannot be read within the inventory bounds')
            with path.open('rb') as handle:
                raw = handle.read(max_file_bytes + 1)
            if len(raw) > max_file_bytes:
                raise ContractError('File grew beyond inventory bounds')
            after = path.stat()
            if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                raise ContractError('Source changed during inventory')
            matches = [kind for kind, rules in classification.items() if _excluded(relative, rules)]
            kind = matches[0] if len(matches) == 1 else 'unknown'
            reasons = ['Explicit classification policy'] if len(matches) == 1 else ['No explicit classification']
            if len(matches) > 1:
                issues.append({'code': 'CLASSIFICATION_CONFLICT', 'path': relative})
                reasons = ['Conflicting classification policies']
            entry = {'path': relative, 'kind': 'file', 'sha256': hashlib.sha256(raw).hexdigest(), 'class': kind, 'reasons': reasons}
            entries.append(entry)
            if (path.name in MANIFESTS and len(matches) <= 1
                    and kind not in {'generated','vendored','historical_copy','runtime_artifact'}
                    and (kind == 'first_party' or not any(part in HINTS for part in PurePosixPath(relative).parts))):
                try:
                    data = _manifest(raw.decode('utf-8'), path.suffix)
                    component = _component(repository, relative, path.name, data)
                    if identity != 'confirmed': component['boundary'] = 'unknown'
                    old = components.get(component['path'])
                    if old:
                        old['manifests'].append(relative); old['evidence_refs'].append('file:'+relative)
                        old['source_roots'] = sorted(set(old['source_roots'] + component['source_roots']))
                        if old['name'] != component['name']:
                            old['boundary'] = 'unknown'; issues.append({'code':'COMPONENT_BOUNDARY_CONFLICT','path':relative})
                    else: components[component['path']] = component
                except (ValueError, UnicodeError, ContractError) as error:
                    issues.append({'code': 'MANIFEST_UNREADABLE', 'path': relative, 'reason': type(error).__name__})
        except (OSError, ContractError) as error:
            issues.append({'code': 'INVENTORY_COVERAGE_GAP', 'path': relative, 'reason': type(error).__name__})
    if not components:
        components['.'] = {'id':repository+':.', 'repository_id':repository, 'path':'.', 'name':None, 'kind':'unknown', 'boundary':'unknown', 'manifests':[], 'evidence_refs':[], 'source_roots':[], 'workspace_members':[]}
    ordered = sorted(components.values(), key=lambda c:c['path'])
    for entry in entries:
        owners = [c for c in ordered if c['path']=='.' or entry['path'].startswith(c['path']+'/')]
        owner = max(owners, key=lambda c:len(c['path'])) if owners else None
        entry['component_id'] = owner['id'] if owner else None
        hint = next((HINTS[part] for part in PurePosixPath(entry['path']).parts if part in HINTS), None)
        entry['classification_hint'] = hint
        if entry['class']=='unknown' and entry['reasons']==['No explicit classification'] and owner and owner['boundary']=='confirmed' and hint is None:
            local = entry['path'] if owner['path']=='.' else entry['path'][len(owner['path'])+1:]
            if any(local.startswith(source+'/') for source in owner['source_roots']) or entry['path'] in owner['manifests']:
                entry.update({'class':'first_party','reasons':['Confirmed package manifest and declared source root']})
    source = [{'path':e['path'],'kind':e['kind'],'sha256':e['sha256']} for e in entries if e['class'] in {'first_party','unknown'}]
    return {'repository_id':repository,'identity':identity,'head':head,'components':ordered,'files':entries,
            'source_digest':payload_digest(source),'local_changes_digest':payload_digest({'index':index,'status':status,'worktree':source}),
            'scope_digest':payload_digest({'paths':[e['path'] for e in entries],'exclusions':patterns,'classification':classification}),
            'exclusions':patterns,'complete':not issues,'quality_issues':issues}
