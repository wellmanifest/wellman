"""Pinned, read-only JSON report adapters. Hashes bind bytes, not authority.

Receipts are supplied separately by a caller that has verified the scanner's
provenance. A report cannot attest itself. Legacy formats remain diagnostic.
No tool, project module, report command or report validator is executed here.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

from wellman.selection_contracts import (
    MAX_DOCUMENT_BYTES,
    ContractError,
    canonical_bytes,
)

ADAPTER_VERSION = 'wellman.evidence/v1'
# Contracts inspected in producer source, not inferred from similar keys.
CONTRACTS = {
    'code2llm': ('0.5.181', 'code2llm.AnalysisResult/v1'),
    'redup': ('0.4.48', 'redup.DuplicationMap/v1'),
    'prefact': ('0.1.69', 'prefact.PipelineResult/v1'),
}
LANGUAGES = {'.py':'python', '.js':'javascript', '.jsx':'javascript', '.ts':'typescript',
             '.tsx':'typescript', '.rs':'rust'}
FEATURES = ('language:python', 'language:javascript', 'language:typescript', 'language:rust',
            'llm-client', 'agent', 'saas-lifecycle', 'graph:relationships', 'side-effects:absent')


def _path(root, value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or '..' in path.parts or '\\' in value:
        raise ContractError('Report path must stay within its artifact root')
    target = root / value
    if any(p.is_symlink() for p in (target, *target.parents) if p == root or root in p.parents):
        raise ContractError('Symlink report is not read')
    return target


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ContractError('Duplicate JSON key')
            result[key] = value
        return result
    data = json.loads(raw, object_pairs_hook=pairs)
    canonical_bytes(data)
    if not isinstance(data, dict):
        raise ContractError('Report must be an object')
    return data


def _shape(tool, data):
    if tool == 'code2llm':
        return isinstance(data.get('project_path'), str) and isinstance(data.get('modules', {}), dict)
    if tool == 'redup':
        return all(isinstance(data.get(k), t) for k,t in [('stats',dict),('summary',dict),('groups',list)])
    if tool == 'prefact':
        return all(isinstance(data.get(k), t) for k,t in [('dry_run',bool),('summary',dict),('issues',list),('fixes',list),('validations',list)])
    return False


def _graph_sources(data, nodes, reported_file, files):
    """Resolve pinned FunctionInfo/FlowNode identities without rewriting bytes.

    code2llm entry_points identify functions. CFG nodes bind to those exact
    functions; source locations belong to FunctionInfo and its declared module.
    Legacy direct-file nodes remain usable, but conflicting bindings never do.
    """
    problems = []
    functions = data.get('functions', {})
    modules = data.get('modules', {})
    if not isinstance(functions, dict):
        return {}, {}, ['Function collection is malformed.']
    bindings = {}
    for identity, function in functions.items():
        if not isinstance(function, dict):
            problems.append('Function identity is malformed.')
            continue
        path = reported_file(function.get('file'))
        module = modules.get(function.get('module')) if isinstance(function.get('module'), str) else None
        if (function.get('qualified_name') != identity or path not in files
                or not isinstance(module, dict) or reported_file(module.get('file')) != path):
            problems.append('Function/module/source identity does not agree.')
            continue
        declared = function.get('cfg_nodes', [])
        if (not isinstance(declared, list) or any(not isinstance(n, str) for n in declared)
                or len(set(declared)) != len(declared)
                or any(n not in nodes or not isinstance(nodes[n], dict)
                       or nodes[n].get('function') != identity for n in declared)):
            problems.append('Function CFG node membership is unresolved.')
            continue
        endpoints_valid = not declared or all(isinstance(function.get(k), str) for k in ('cfg_entry', 'cfg_exit'))
        for field, kind in (('cfg_entry', 'ENTRY'), ('cfg_exit', 'EXIT')):
            endpoint = function.get(field)
            if endpoint is not None and (not isinstance(endpoint, str) or endpoint not in declared
                    or nodes[endpoint].get('type') != kind):
                endpoints_valid = False
        if not endpoints_valid:
            problems.append('Function CFG entry/exit identity is unresolved.')
            continue
        bindings[identity] = (path, set(declared), function.get('cfg_entry'))
    resolved = {}
    for identity, node in nodes.items():
        if not isinstance(node, dict) or node.get('id', identity) != identity:
            problems.append('CFG node identity is malformed.')
            continue
        direct = reported_file(node.get('file'))
        function = node.get('function')
        if function is not None:
            binding = bindings.get(function) if isinstance(function, str) else None
            if (binding is None or identity not in binding[1]
                    or ('file' in node and direct != binding[0])):
                problems.append('CFG node/function/source identity does not agree.')
                continue
            direct = binding[0]
        if direct not in files:
            problems.append('CFG node has no confirmed first-party source.')
            continue
        resolved[identity] = dict(node, file=direct)
    entries = {identity: value[2] for identity, value in bindings.items()
               if value[2] in resolved}
    return resolved, entries, problems


def normalize_report(tool, artifact_root, relative_path, inventory, *, version=None,
                     output_schema=None, receipt=None, outcome=None, component_id=None, source_root=None):
    """Return observation-compatible fields and diagnostic provenance.

    Receipt fields bind tool/version/schema, bytes, source/index state, scope,
    configuration and environment. Missing provenance never proves absence.
    ``outcome`` represents an independently observed process failure or timeout;
    report text is never treated as a process outcome or a validation receipt.
    """
    root = Path(artifact_root).absolute()
    if receipt is not None and not isinstance(receipt, dict):
        raise ContractError('Receipt must be a separate object')
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ContractError('Artifact root must not traverse a symlink')
    receipt = receipt or {}
    stamp = receipt.get('started_at', '1970-01-01T00:00:00Z')
    end = receipt.get('finished_at', stamp)
    ref = tool + ':' + relative_path
    stage = {'id': ref, 'tool': tool, 'component_id': component_id, 'started_at': stamp,
                 'finished_at': end, 'status': 'partial', 'exit_code': receipt.get('exit_code'),
                 'truncated': False, 'coverage': 'unknown', 'errors': [], 'artifact_refs': []}
    result = {'tool':{'id': tool, 'version': version, 'adapter_version': ADAPTER_VERSION,
                         'output_schema': output_schema, 'configuration_digest': receipt.get('configuration_digest'),
                         'environment_digest': receipt.get('environment_digest'),
                         'effective_exclusions': receipt.get('effective_exclusions', [])},
              'stage':stage, 'artifacts':[], 'features':[], 'metrics':[], 'quality_issues':[]}
    def issue(code, message, refs=None):
        result['quality_issues'].append({'code': code, 'severity': 'warning', 'message': message,
            'affected_refs': refs or [ref], 'next_action': 'Re-scan with a pinned producer and explicit source/scope receipt.'})
        if code not in stage['errors']:
            stage['errors'].append(code)
    def finish():
        # Every unsupported/partial input preserves unknown business capabilities.
        for c in inventory['components']:
            if component_id is not None and c['id'] != component_id:
                continue
            known = {f['id'] for f in result['features'] if f['component_id'] == c['id']}
            for feature in FEATURES:
                if feature not in known:
                    result['features'].append({'id': feature,'component_id': c['id'],'state': 'unknown',
                        'coverage': 'unknown','evidence_refs': [],'reasons': ['NO_SUFFICIENT_EVIDENCE']})
        result['features'].sort(key=lambda f:(f['component_id'],f['id']))
        return result
    if outcome and (outcome.get('timeout') or outcome.get('exit_code') not in (None,0)):
        stage.update(status='failed', exit_code=outcome.get('exit_code'))
        issue('TOOL_TIMEOUT' if outcome.get('timeout') else 'TOOL_FAILED','Scanner process did not complete successfully.')
        return finish()
    try:
        target = _path(root, relative_path)
        if not target.exists():
            stage['status'] = 'missing'; issue('REPORT_MISSING','Report not available.'); return finish()
        if not target.is_file():
            raise ContractError('Report must be a regular file')
        before = target.stat()
        with target.open('rb') as handle:
            raw = handle.read(MAX_DOCUMENT_BYTES + 1)
        after = target.stat()
        if len(raw) > MAX_DOCUMENT_BYTES:
            raise ContractError('Report exceeds byte budget')
        if (before.st_size,before.st_mtime_ns) != (after.st_size,after.st_mtime_ns):
            raise ContractError('Report changed while reading')
        digest = hashlib.sha256(raw).hexdigest()
        artifact = {'id': ref,'path': relative_path,'media_type': 'application/json','size_bytes': len(raw),'sha256': digest,
            'producer': tool,'origin_observation_id': None,'freshness': 'legacy_unverified'}
        result['artifacts'].append(artifact); stage['artifact_refs']=[ref]
        if target.suffix != '.json':
            stage['status']='unsupported'; issue('DIAGNOSTIC_FORMAT','TOON or summaries are diagnostic only.'); return finish()
        data = _json(raw)
    except (OSError, ValueError, RecursionError) as error:
        stage['status']='failed'; issue('REPORT_INVALID','Report cannot be safely parsed: '+type(error).__name__); return finish()
    expected = CONTRACTS.get(tool)
    if not expected or (version is not None and version != expected[0]) or (output_schema is not None and output_schema != expected[1]) or data.get('schema', expected[1] if expected else None) != (expected[1] if expected else None) or not _shape(tool,data):
        stage['status']='unsupported'; issue('REPORT_UNSUPPORTED','Unknown producer version, schema or shape.'); return finish()
    matches = (version, output_schema) == expected and bool(receipt.get('observation_id'))
    for key, value in [('sha256',digest),('tool',tool),('version',version),('output_schema',output_schema),
                       ('source_digest',inventory['source_digest']),('local_changes_digest',inventory['local_changes_digest']),
                       ('head',inventory['head']),('scope_digest',inventory['scope_digest'])]:
        matches = matches and key in receipt and receipt[key] == value
    matches = matches and inventory['complete'] and inventory['identity']=='confirmed'
    matches = matches and all(isinstance(receipt.get(k),str) and re.fullmatch('[0-9a-f]{64}',receipt[k]) for k in ('configuration_digest','environment_digest'))
    matches = matches and type(receipt.get('exit_code')) is int and receipt.get('exit_code') == 0 and all(receipt.get(k) for k in ('started_at','finished_at'))
    if matches:
        artifact.update(origin_observation_id=receipt['observation_id'],freshness='verified')
        stage['coverage'] = 'complete' if receipt.get('coverage')=='complete' else 'partial'
        stage['status'] = 'complete' if stage['coverage']=='complete' else 'partial'
    else:
        artifact['origin_observation_id'] = receipt.get('observation_id')
        if receipt and any(receipt.get(k)!=inventory[k] for k in ('source_digest','local_changes_digest','head','scope_digest') if k in receipt):
            artifact['freshness']='stale'; issue('SOURCE_CHANGED_DURING_SCAN','Receipt does not bind the current source and scope.')
        else:
            issue('PROVENANCE_UNVERIFIED','Legacy bytes have no coherent source and scope receipt.')
    stage['truncated'] = receipt.get('truncated') is True
    if stage['truncated']:
        stage.update(status='partial',coverage='partial'); issue('REPORT_TRUNCATED','Producer reported truncation.')
    def reported_file(value):
        if not isinstance(value,str) or '\\' in value or '..' in PurePosixPath(value).parts:
            return None
        path = PurePosixPath(value)
        if path.is_absolute():
            if source_root is None:
                return None
            try:
                path = path.relative_to(PurePosixPath(str(Path(source_root).absolute())))
            except ValueError:
                return None
        return path.as_posix()
    files = {f['path']:f for f in inventory['files'] if f.get('class')=='first_party' and f.get('sha256')}
    def metric(name, definition, unit, value):
        if type(value) in (int,float):
            result['metrics'].append({'name': name,'definition': definition,'unit': unit,'tool': tool,
                'component_id': component_id,'scope_digest': inventory['scope_digest'],'value': value})
    if tool == 'redup':
        metric('duplicate_groups','Groups of duplicate source fragments emitted by redup, before report selection.','fragment_group',data['summary'].get('total_groups'))
        selection = data.get('selection', {})
        if not isinstance(selection,dict) or selection.get('truncated') or selection.get('omitted_groups',0) or (not selection and data['summary'].get('total_groups') != len(data['groups'])):
            stage.update(status='partial',coverage='partial',truncated=True); issue('REPORT_TRUNCATED','Duplicate group listing is incomplete.')
        eligible = 0
        for group in data['groups']:
            if not isinstance(group,dict) or not isinstance(group.get('fragments'),list):
                issue('REPORT_INVALID_GROUP','Invalid duplicate group.'); stage['status']='partial'; continue
            paths = [reported_file(f.get('file')) for f in group['fragments'] if isinstance(f,dict)]
            if len(paths)>=2 and len(paths)==len(group['fragments']) and all(isinstance(p,str) and p in files and (component_id is None or files[p]['component_id']==component_id) for p in paths):
                eligible += 1
        metric('first_party_candidate_groups','Returned groups whose every fragment is positively classified first_party; diagnostic candidates only.','fragment_group',eligible)
    elif tool == 'prefact':
        metric('reported_issues','Issues reported by prefact; this is not a conformance attestation.','issue',data['summary'].get('issues'))
        if not data['dry_run'] or any(isinstance(f,dict) and f.get('applied') for f in data['fixes']):
            stage.update(status='partial',coverage='partial'); issue('REPORT_HAS_EFFECTS','Report describes applied fixes rather than an observation-only scan.')
    else:
        modules = data.get('modules',{})
        observed = {}
        for module in modules.values():
            if not isinstance(module,dict) or not isinstance(module.get('file'),str):
                stage['status']='partial'; issue('REPORT_INVALID_MODULE','Module has no usable file identity.'); continue
            entry = files.get(reported_file(module['file']))
            if entry is None or (component_id is not None and entry['component_id'] != component_id):
                continue
            language = LANGUAGES.get(PurePosixPath(module['file']).suffix)
            if language:
                observed.setdefault(entry['component_id'],set()).add('language:'+language)
            imports = module.get('imports',[])
            if isinstance(imports,list) and any(isinstance(i,str) and i.split('.')[0] in ('openai','anthropic','subllm') for i in imports):
                observed.setdefault(entry['component_id'],set()).add('llm-client')
        nodes,edges,entry_points = data.get('nodes',{}),data.get('edges',[]),data.get('entry_points',[])
        graph_ok = isinstance(nodes,dict) and isinstance(edges,list) and isinstance(entry_points,list)
        if not graph_ok:
            issue('GRAPH_INVALID','Graph collections have invalid shapes.')
        else:
            resolved, function_entries, binding_problems = _graph_sources(data, nodes, reported_file, files)
            if binding_problems:
                graph_ok=False; issue('GRAPH_INVALID_BINDING',' '.join(sorted(set(binding_problems))))
            outside = any(not isinstance(p,str) or p not in resolved and p not in function_entries for p in entry_points)
            if outside and receipt.get('graph_scope') != 'declared_subgraph':
                graph_ok=False; issue('GRAPH_SCOPE_UNDECLARED','Entry points cannot resolve to CFG nodes or function CFG entries without a declared subgraph.')
            for edge in edges:
                if not isinstance(edge,dict) or not isinstance(edge.get('source'),str) or not isinstance(edge.get('target'),str) or edge['source'] not in nodes or edge['target'] not in nodes:
                    graph_ok=False; issue('GRAPH_UNRESOLVED_EDGE','An edge cannot be resolved within the graph.'); continue
                source,target = resolved.get(edge['source']),resolved.get(edge['target'])
                if not isinstance(source,dict) or not isinstance(target,dict):
                    graph_ok=False; issue('GRAPH_INVALID','Node identity is malformed.'); continue
                left=LANGUAGES.get(PurePosixPath(str(source.get('file',''))).suffix)
                right=LANGUAGES.get(PurePosixPath(str(target.get('file',''))).suffix)
                bridges=receipt.get('bridges',[])
                bridge=any(isinstance(b,dict) and isinstance(b.get('path'),str) and b.get('source')==edge['source'] and b.get('target')==edge['target'] and reported_file(b.get('path')) in files and b.get('sha256')==files[reported_file(b['path'])]['sha256'] for b in bridges) if isinstance(bridges,list) else False
                if left and right and left!=right and not bridge:
                    graph_ok=False; issue('GRAPH_CROSS_LANGUAGE_UNVERIFIED','Cross-language name resolution lacks source-bound bridge evidence.')
            if len(resolved) != len(nodes):
                graph_ok=False; issue('GRAPH_NONPRODUCT_OR_UNKNOWN','Graph includes files without positive first-party classification.')
            if nodes and graph_ok and matches and receipt.get('graph_scope')=='complete' and stage['status']=='complete':
                for c in inventory['components']:
                    if (component_id is None or c['id']==component_id) and any(isinstance(n,dict) and isinstance(n.get('file'),str) and reported_file(n['file']) in files and files[reported_file(n['file'])]['component_id']==c['id'] for n in resolved.values()):
                        result['features'].append({'id': 'graph:relationships','component_id': c['id'],'state': 'present','coverage': 'complete','evidence_refs': [ref],'reasons': ['SOURCE_BOUND_GRAPH']})
        if not graph_ok or receipt.get('graph_scope') != 'complete':
            if stage['status']=='complete':stage.update(status='partial',coverage='partial')
            issue('GRAPH_PARTIAL','Graph is diagnostic; coverage is partial or undeclared.')
        # A static purity label is never proof of the absence of side effects.
        if b'pure' in raw.lower():
            issue('PURITY_LABEL_UNVERIFIED','Purity labels are not side-effect attestations.')
        if matches:
            for cid,features in observed.items():
                for feature in sorted(features):
                    result['features'].append({'id': feature,'component_id': cid,'state': 'present','coverage': 'partial','evidence_refs': [ref],'reasons': ['FIRST_PARTY_MODULE']})
        metric('classes','Class symbols emitted by code2llm; not duplicate fragment groups.','class_symbol',len(data.get('classes',{})) if isinstance(data.get('classes',{}),dict) else None)
    return finish()
