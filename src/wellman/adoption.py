"""Language-independent registration of requirements, not conformance claims."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from wellman.registry import PROFILES_CATALOG, get_standard


SCHEMA = 'wellman.standard-requirements/v1'


def safe_path(path):
    """Reject symlinks before normalizing '..' or resolving a write target."""
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    cursor = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f'Refusing symlink: {cursor}')
    return candidate.resolve()


def repository_root(path, *, bootstrap=False):
    """Select the active Git checkout, never the shared primary checkout."""
    root = safe_path(path)
    if not root.is_dir():
        raise ValueError(f'Project root must exist: {root}')
    # A caller's Git overrides must not redirect discovery to another checkout.
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith('GIT_')}
    try:
        result = subprocess.run(
            ['git', '-C', str(root), 'rev-parse', '--show-toplevel'],
            env=environment, capture_output=True, text=True, check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError('Cannot discover repository root with Git') from error
    if result.returncode == 0:
        discovered = safe_path(result.stdout.strip())
        try:
            root.relative_to(discovered)
        except ValueError as error:
            raise ValueError('Git discovered a working tree outside the requested path') from error
        return discovered
    # Bootstrap is explicit and must not hide a broken Git checkout.
    if any((parent / '.git').exists() or (parent / '.git').is_symlink()
           for parent in (root, *root.parents)):
        raise ValueError('Git repository discovery failed; repair its metadata first')
    try:
        bare = subprocess.run(
            ['git', '-C', str(root), 'rev-parse', '--is-bare-repository'],
            env=environment, capture_output=True, text=True, check=False, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError('Cannot discover repository root with Git') from error
    if bare.returncode == 0:
        raise ValueError('A working tree is required; bare repositories are not adoption targets')
    if not bootstrap:
        raise ValueError('Not inside a Git working tree; use --bootstrap for an explicit non-Git directory')
    return root


def _object(path):
    if path.is_symlink():
        raise ValueError(f'Refusing symlink: {path}')
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError(f'Expected JSON object: {path}')
    return data


def expand_profiles(profiles):
    """Expand inherited requirements; cycles and unknown profiles fail closed."""
    requirements, done, active = {}, set(), set()

    def visit(name):
        if name in active:
            raise ValueError(f'Profile inheritance cycle: {name}')
        if name in done:
            return
        if name not in PROFILES_CATALOG:
            raise ValueError(f'Unknown profile: {name}')
        active.add(name)
        profile = PROFILES_CATALOG[name]
        for parent in profile.extends:
            visit(parent)
        for item in profile.requirements:
            if get_standard(item['id']) is None or item['minimumLevel'] not in {f'S{i}' for i in range(6)}:
                raise ValueError(f'Invalid profile requirement: {item}')
            requirements[item['id']] = max(requirements.get(item['id'], 'S0'), item['minimumLevel'])
        active.remove(name)
        done.add(name)

    for name in profiles:
        visit(name)
    return requirements


def register(root, profiles=(), *, standards=(), dry_run=False):
    """Add required standards without replacing manifests, pins or evidence.

    Baseline applies even to unknown languages and documentation-only projects.
    Roles/profiles and deployment contracts add capabilities; file extensions
    never decide whether governance is required.
    """
    root = safe_path(root)
    if not root.is_dir():
        raise ValueError(f'Project root must exist: {root}')
    governance = root / '.governance'
    if governance.is_symlink():
        raise ValueError(f'Refusing symlink: {governance}')
    path = governance / 'standard-requirements.json'
    if path.is_symlink():
        raise ValueError(f'Refusing symlink: {path}')
    before = path.read_bytes() if path.exists() else None
    existing = json.loads(before) if before is not None else {}
    if not isinstance(existing, dict):
        raise ValueError('Requirements must be a JSON object')
    selected = {'baseline', *profiles}
    for name in ('manifest.json', 'standard-adoption.json'):
        manifest = _object(governance / name)
        profile = manifest.get('profile')
        if profile is not None:
            if not isinstance(profile, str) or profile not in PROFILES_CATALOG:
                raise ValueError(f'Unknown profile in {name}: {profile!r}; register it in the catalog first')
            selected.add(profile)
        role = manifest.get('repositoryRole')
        if isinstance(role, str) and role in PROFILES_CATALOG:
            selected.add(role)
    if any((root / marker).is_file() for marker in
           ('Dockerfile', 'compose.yml', 'compose.yaml', 'docker-compose.yml', 'docker-compose.yaml')):
        selected.add('deployment')
    if (root / 'operations' / 'index.json').is_file():
        selected.add('domain-pack')
    if existing and existing.get('schema') != SCHEMA:
        raise ValueError('Unknown requirements schema; refusing to overwrite')
    old_profiles = existing.get('profiles', [])
    old_items = existing.get('requirements', [])
    if not isinstance(old_profiles, list) or not all(isinstance(p, str) for p in old_profiles):
        raise ValueError('profiles must be an array of strings')
    if not isinstance(old_items, list):
        raise ValueError('requirements must be an array')
    selected.update(old_profiles)
    required = expand_profiles(selected)
    for name in standards:
        standard = get_standard(name)
        if standard is None:
            raise ValueError(f'Unknown standard: {name}')
        required[standard.id] = max(required.get(standard.id, 'S0'), standard.minimum_level)
    items = {}
    for item in old_items:
        if (not isinstance(item, dict) or not isinstance(item.get('id'), str)
                or not item['id'] or not isinstance(item.get('minimumLevel'), str)
                or item['minimumLevel'] not in {f'S{i}' for i in range(6)}):
            raise ValueError('Invalid existing requirement')
        if item['id'] in items:
            raise ValueError(f"Duplicate requirement: {item['id']}")
        items[item['id']] = dict(item)
    for standard, level in required.items():
        item = items.setdefault(standard, {'id': standard, 'minimumLevel': level})
        item['minimumLevel'] = max(item['minimumLevel'], level)
    result = {**existing, 'schema': SCHEMA, 'profiles': sorted(selected),
              'requirements': [items[key] for key in sorted(items)]}
    changed = existing != result
    if changed and not dry_run:
        governance.mkdir(exist_ok=True)
        # Exclusive lock prevents two Wellman writers from losing an update.
        lock = governance / '.standard-requirements.lock'
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        temporary = None
        try:
            if path.is_symlink() or (path.read_bytes() if path.exists() else None) != before:
                raise ValueError('Requirements changed concurrently; retry from a fresh observation')
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=governance,
                                             prefix='.requirements-', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(result, stream, indent=2, ensure_ascii=False)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            os.close(descriptor)
            if temporary is not None and temporary.exists():
                temporary.unlink()
            lock.unlink()
    # Local OneDev + Validator publication is the default for every repository;
    # only an existing adopter restriction is kept, never replaced.
    from wellman.local_ci import ensure_default_policy
    local_ci = ensure_default_policy(root, dry_run=dry_run)
    return {'changed': changed or local_ci['changed'], 'dry_run': dry_run, 'path': str(path),
            'registration': result, 'conformance': 'unverified',
            'localCiPublication': local_ci}
