"""Offline candidate URIprocess multipack validation; no publication or execution.

A multipack describes one operational capability with multiple language bindings.
This Wellman candidate is not a published revision of wellmanifest/uriprocess.
Run: python -m wellman.multipack path/to/multipack.json

Exact process URI namespaces are retained. Versions default to lockstep;
version_policy='independent' permits separate stable binding versions.
A binding with publish=false stays out of declared_publications, including
an internal Rust core. These declarations never grant publication authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from .selection_contracts import ContractError, _check, canonical_bytes

MAX_BYTES = 1024 * 1024
SCHEMA = Path(__file__).with_name('schemas') / 'operational-multipack.schema.json'


def validate(document):
    """Return deterministic findings about declarations, never runtime conformance."""
    findings = []
    def add(code, path, message):
        findings.append({'code': code, 'path': path, 'message': message})
    try:
        encoded = canonical_bytes(document)
        if len(encoded) > MAX_BYTES:
            raise ContractError('Multipack exceeds one MiB')
        schema = json.loads(SCHEMA.read_text())
        _check(document, schema, schema)
    except (ContractError, RecursionError) as exc:
        return {'ok': False, 'authority': 'none', 'findings': [
            {'code': 'MULTIPACK-SCHEMA', 'path': '$', 'message': str(exc)}]}

    operations = document['operations']
    bindings = document['bindings']
    op_ids = [o['id'] for o in operations]
    binding_ids = [b['id'] for b in bindings]
    for label, ids in [('operations', op_ids), ('bindings', binding_ids)]:
        if len(set(ids)) != len(ids):
            add('MULTIPACK-DUPLICATE', label, 'Identifiers must be unique')
    for binding in bindings:
        path = 'bindings.' + binding['id']
        entry = binding['entry']
        if (entry.startswith('/') or ':' in entry.split('/')[0] or
                any(ord(c) < 32 or ord(c) == 127 for c in entry) or '\\' in entry or
                any(part in ('', '.', '..') for part in entry.split('/'))):
            add('MULTIPACK-PATH', path, 'Entry must be a normalized relative package path')
        if not set(binding['operations']) <= set(op_ids):
            add('MULTIPACK-REFERENCE', path, 'Unknown operation reference')
        if (document.get('version_policy', 'lockstep') == 'lockstep'
                and binding['version'] != document['version']):
            add('MULTIPACK-VERSION', path, 'Bindings must use the family version in this profile')
        expected = {'rust': 'cargo', 'python': 'pypi', 'node': 'npm'}[binding['language']]
        if binding['registry'] != expected:
            add('MULTIPACK-REGISTRY', path, 'Language and registry do not match')
    for binding in bindings:
        if set(binding['operations']) != set(op_ids):
            add('MULTIPACK-COVERAGE', 'bindings.' + binding['id'], 'Every binding must expose the family operation set')
    identities = [(b['registry'], b['package']) for b in bindings]
    if len(set(identities)) != len(identities):
        add('MULTIPACK-DUPLICATE', 'bindings', 'Registry/package identities must be unique')
    cores = [b for b in bindings if b['implementation'] == 'core']
    if len(cores) != 1 or cores[0]['language'] != document['core_language']:
        add('MULTIPACK-CORE', 'bindings', 'Declare exactly one core matching core_language')
    for operation in operations:
        path = 'operations.' + operation['id']
        try:
            uri = urlsplit(operation['uri'])
            _ = uri.port  # Reject malformed authorities consistently with CLI validation.
        except ValueError:
            add('MULTIPACK-URI', path, 'Malformed process URI')
            continue
        if 'pure' in operation['effects'] and len(operation['effects']) > 1:
            add('MULTIPACK-EFFECTS', path, 'Pure cannot be combined with effectful declarations')
        if (not uri.scheme or not uri.hostname or not uri.path.startswith('/') or
                uri.query or uri.fragment or uri.username or uri.password or '%' in operation['uri'] or
                '\\' in operation['uri'] or any(ord(c) < 32 or ord(c) == 127 for c in operation['uri']) or
                any(p in ('', '.', '..') for p in uri.path[1:].split('/'))):
            add('MULTIPACK-URI', path, 'Use an exact process URI without query, fragment or unsafe path')
        adapters = [a for a in document['adapters'] if a['operation'] == operation['id']]
        if not adapters:
            add('MULTIPACK-ADAPTER', path, 'Every operation requires a process adapter')
        if not any(operation['id'] in b['operations'] for b in bindings):
            add('MULTIPACK-COVERAGE', path, 'Operation is not exposed by any binding')
    uris = [o['uri'] for o in operations]
    if len(set(uris)) != len(uris):
        add('MULTIPACK-DUPLICATE', 'operations', 'Process URIs must be unique')
    for adapter in document['adapters']:
        path = 'adapters.' + adapter['operation']
        binding = next((b for b in bindings if b['id'] == adapter['binding']), None)
        if adapter['operation'] not in op_ids or binding is None:
            add('MULTIPACK-REFERENCE', path, 'Unknown operation or binding')
        elif adapter['operation'] not in binding['operations']:
            add('MULTIPACK-COVERAGE', path, 'Adapter binding does not expose this operation')
    digest = hashlib.sha256(encoded).hexdigest()
    return {'ok': not findings, 'authority': 'none', 'contract_sha256': digest,
            'validation': 'declarations-only', 'findings': findings,
            'declared_publications': [
                {'binding': b['id'], 'registry': b['registry'], 'package': b['package'], 'version': b['version']}
                for b in bindings if b.get('publish', True)
            ] if not findings else []}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    args = parser.parse_args(argv)
    try:
        with args.manifest.open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('Multipack exceeds one MiB')
        def pairs(items):
            obj = {}
            for key, value in items:
                if key in obj:
                    raise ValueError('Duplicate JSON key: ' + key)
                obj[key] = value
            return obj
        result = validate(json.loads(data, object_pairs_hook=pairs))
    except (OSError, ValueError, RecursionError) as exc:
        result = {'ok': False, 'authority': 'none', 'findings': [
            {'code': 'MULTIPACK-INPUT', 'path': '$', 'message': str(exc)}]}
    print(json.dumps(result, sort_keys=True))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
