"""Cross-binding declarations must not silently change operational semantics."""
from copy import deepcopy
import json

import pytest

from wellman.multipack import main, validate


def manifest():
    return {
        'schema': 'wellman.operational-multipack/v1', 'id': 'netprobe',
        'version': '0.1.0', 'core_language': 'rust',
        'source': {'repository': 'https://github.com/dockuri/uri-netprobe', 'revision': 'a' * 40},
        'contract': {k: 'b' * 64 for k in ('input_sha256', 'output_sha256', 'conformance_vectors_sha256')},
        'operations': [{'id': 'scan', 'uri': 'proc://netprobe/scan/v1', 'effects': ['read', 'network']}],
        'bindings': [
            {'id': 'rust', 'language': 'rust', 'implementation': 'core', 'registry': 'cargo',
             'package': 'uri-netprobe-core', 'version': '0.1.0', 'entry': 'src/lib.rs', 'operations': ['scan']},
            {'id': 'python', 'language': 'python', 'implementation': 'native-extension', 'registry': 'pypi',
             'package': 'uri-netprobe', 'version': '0.1.0', 'entry': 'uri_netprobe/__init__.py', 'operations': ['scan']},
            {'id': 'node', 'language': 'node', 'implementation': 'native-extension', 'registry': 'npm',
             'package': '@dockuri/netprobe', 'version': '0.1.0', 'entry': 'index.js', 'operations': ['scan']},
        ],
        'adapters': [{'operation': 'scan', 'binding': 'rust', 'transport': 'stdin-json'}],
    }


def test_family_is_declarative_and_deterministic():
    d = manifest(); before = deepcopy(d)
    result = validate(d)
    assert result['ok'] and result['authority'] == 'none'
    assert result['validation'] == 'declarations-only'
    assert result == validate(d) and d == before


@pytest.mark.parametrize('field,value,code', [
    ('registry', 'npm', 'MULTIPACK-REGISTRY'),
    ('version', '0.2.0', 'MULTIPACK-VERSION'),
    ('entry', '../escape.py', 'MULTIPACK-PATH'),
    ('entry', '/tmp/escape.py', 'MULTIPACK-PATH'),
    ('entry', 'C:/escape.py', 'MULTIPACK-PATH'),
    ('entry', 'src/invalid\x00.rs', 'MULTIPACK-PATH'),
    ('entry', 'src//lib.rs', 'MULTIPACK-PATH'),
    ('operations', ['missing'], 'MULTIPACK-REFERENCE'),
])
def test_reject_inconsistent_binding(field, value, code):
    d = manifest(); d['bindings'][0][field] = value
    assert code in {f['code'] for f in validate(d)['findings']}


@pytest.mark.parametrize('uri', ['proc://netprobe/../scan', 'proc://netprobe/scan?q=x',
                                  'proc://netprobe/scan#x', 'proc://netprobe/%2e%2e/scan', 'proc://[broken/scan', 'proc://netprobe:bad/scan'])
def test_reject_noncanonical_process_uri(uri):
    d = manifest(); d['operations'][0]['uri'] = uri
    assert not validate(d)['ok']


def test_adapter_must_bind_a_real_exposed_operation():
    d = manifest(); d['adapters'][0]['binding'] = 'missing'
    assert not validate(d)['ok']
    d = manifest(); d['bindings'].append({**d['bindings'][1], 'id': 'other', 'package': 'other', 'operations': ['status']})
    d['adapters'][0]['binding'] = 'other'
    assert 'MULTIPACK-COVERAGE' in {f['code'] for f in validate(d)['findings']}


def test_closed_schema_and_duplicate_identities():
    d = manifest(); d['grant'] = 'self-approved'
    assert not validate(d)['ok']
    d = manifest(); d['bindings'].append({**d['bindings'][1], 'id': 'second-python'})
    assert 'MULTIPACK-DUPLICATE' in {f['code'] for f in validate(d)['findings']}


def test_multiple_or_missing_cores_rejected():
    d = manifest(); d['bindings'][1]['implementation'] = 'core'
    assert not validate(d)['ok']
    d = manifest(); d['bindings'].pop(0)
    assert not validate(d)['ok']


def test_cli_has_stable_machine_readable_results(tmp_path, capsys):
    p = tmp_path / 'contract.json'; p.write_text(json.dumps(manifest()))
    assert main([str(p)]) == 0
    assert json.loads(capsys.readouterr().out)['authority'] == 'none'
    p.write_text('{"schema":"one","schema":"two"}')
    assert main([str(p)]) == 1
    assert json.loads(capsys.readouterr().out)['findings'][0]['code'] == 'MULTIPACK-INPUT'


def test_pure_is_not_an_execution_effect():
    d = manifest(); d['operations'][0]['effects'] = ['pure', 'network']
    assert 'MULTIPACK-EFFECTS' in {f['code'] for f in validate(d)['findings']}


@pytest.mark.parametrize('language', ['python', 'node'])
def test_rust_is_optional_when_family_has_another_shared_core(language):
    d = manifest(); d['bindings'] = [b for b in d['bindings'] if b['language'] != 'rust']
    d['core_language'] = language
    for b in d['bindings']:
        b['implementation'] = 'core' if b['language'] == language else 'process-client'
    d['adapters'][0]['binding'] = language
    assert validate(d)['ok']
    d['core_language'] = 'rust'
    assert not validate(d)['ok']


def test_rust_client_does_not_implicitly_become_the_core():
    d = manifest(); d['core_language'] = 'python'
    d['bindings'][0]['implementation'] = 'process-client'
    d['bindings'][1]['implementation'] = 'core'
    assert validate(d)['ok']
    d['bindings'][0]['implementation'] = 'core'
    assert not validate(d)['ok']


@pytest.mark.parametrize('uri', [
    'dockuri://local/network/scan/v1',
    'taskand://operations/netprobe/scan',
    'uriloop+json://local/netprobe/scan',
])
def test_foreign_uri_namespace_is_preserved(uri):
    d = manifest(); d['operations'][0]['uri'] = uri; before = deepcopy(d)
    result = validate(d)
    assert result['ok'] and result['authority'] == 'none'
    assert d == before
    other = deepcopy(d); other['operations'][0]['uri'] = 'proc://netprobe/scan/v1'
    assert result['contract_sha256'] != validate(other)['contract_sha256']


def test_independent_versions_are_explicit_and_keep_lockstep_as_default():
    d = manifest(); d['bindings'][1]['version'] = '1.2.3'
    assert 'MULTIPACK-VERSION' in {f['code'] for f in validate(d)['findings']}
    d['version_policy'] = 'independent'; before = deepcopy(d)
    assert validate(d)['ok'] and d == before
    d['version_policy'] = 'lockstep'
    assert 'MULTIPACK-VERSION' in {f['code'] for f in validate(d)['findings']}


def test_internal_core_is_excluded_from_declared_publications():
    d = manifest(); d['bindings'][0]['publish'] = False; before = deepcopy(d)
    result = validate(d)
    assert result['ok'] and result['validation'] == 'declarations-only'
    assert result['declared_publications'] == [
        {'binding': b['id'], 'registry': b['registry'], 'package': b['package'], 'version': b['version']}
        for b in d['bindings'][1:]
    ]
    assert d == before and result['authority'] == 'none'


@pytest.mark.parametrize('field,value', [('version_policy', 'auto'), ('publish', 'false'), ('publish', 0)])
def test_publication_policy_rejects_unknown_or_ambiguous_values(field, value):
    d = manifest()
    if field == 'publish':
        d['bindings'][0][field] = value
    else:
        d[field] = value
    assert not validate(d)['ok']


@pytest.mark.parametrize('uri', [
    'dockuri://:80/scan', 'taskand://local:bad/scan', 'dockuri:///scan',
    'dockuri://local', 'dockuri://local//scan', 'dockuri://local/../scan',
    'dockuri://user:secret@local/scan', 'dockuri://local/scan?q=1',
    'uriloop://local/scan#x', 'dockuri://local/%2fscan',
    'dockuri://loc\\al/scan', 'dockuri://local/sc\x00an',
])
def test_foreign_uri_still_requires_safe_exact_identity(uri):
    d = manifest(); d['operations'][0]['uri'] = uri
    result = validate(d)
    assert not result['ok']
    assert result.get('declared_publications', []) == []


def test_default_publication_declarations_include_all_bindings_without_authority():
    d = manifest(); result = validate(d)
    assert result['ok'] and result['authority'] == 'none'
    assert [b['binding'] for b in result['declared_publications']] == ['rust', 'python', 'node']
    d['bindings'][0]['registry'] = 'npm'
    assert validate(d)['declared_publications'] == []
