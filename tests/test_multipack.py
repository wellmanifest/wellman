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
