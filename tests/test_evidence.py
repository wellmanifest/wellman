import hashlib
import json
from pathlib import Path

import pytest

from wellman.evidence import CONTRACTS, normalize_report
from wellman.selection_contracts import ContractError


@pytest.fixture
def inventory():
    return {'identity':'confirmed','head':'a'*40,'source_digest':'1'*64,'local_changes_digest':'2'*64,
        'scope_digest':'3'*64,'complete':True,'components':[{'id':'repo:.'}],
        'files':[{'path':'src/a.py','class':'first_party','sha256':'4'*64,'component_id':'repo:.'},
                 {'path':'src/b.js','class':'first_party','sha256':'5'*64,'component_id':'repo:.'},
                 {'path':'vendor/c.py','class':'vendored','sha256':'6'*64,'component_id':'repo:.'}]}


def report(tool='code2llm'):
    if tool == 'code2llm':
        return {'project_path':'/repo','modules':{'a':{'file':'src/a.py','imports':['openai']},'c':{'file':'vendor/c.py','imports':['anthropic']}},
                'nodes':{'a':{'file':'src/a.py'},'b':{'file':'src/a.py'}},'edges':[{'source':'a','target':'b'}],'entry_points':['a'],'classes':{}}
    if tool == 'redup':
        return {'stats':{},'summary':{'total_groups':1443},'groups':[{'fragments':[{'file':'src/a.py'},{'file':'vendor/c.py'}]}, {'fragments':[{'file':'src/a.py'},{'file':'src/b.js'}]}]}
    return {'dry_run':True,'summary':{'issues':3},'issues':[],'fixes':[],'validations':[]}


def load(tmp_path, inventory, tool='code2llm', data=None, trusted=True, **overrides):
    data=report(tool) if data is None else data
    raw=json.dumps(data).encode();(tmp_path/'report.json').write_bytes(raw)
    version,schema=CONTRACTS[tool]
    receipt={'observation_id':'scan-1','tool':tool,'version':version,'output_schema':schema,
        'sha256':hashlib.sha256(raw).hexdigest(),'started_at':'2026-10-08T00:00:00Z',
        'finished_at':'2026-10-08T00:01:00Z','exit_code':0,'coverage':'complete','graph_scope':'complete',
        'configuration_digest':'7'*64,'environment_digest':'8'*64,
        **{k:inventory[k] for k in ['head','source_digest','local_changes_digest','scope_digest']},**overrides}
    return normalize_report(tool,tmp_path,'report.json',inventory,version=version,output_schema=schema,receipt=receipt if trusted else None)


def codes(result):return {i['code'] for i in result['quality_issues']}
def feature(result,key):return next(f for f in result['features'] if f['id']==key)


def test_source_bound_first_party_import_is_client_not_agent_or_saas(tmp_path,inventory):
    r=load(tmp_path,inventory)
    assert r['stage']['status']=='complete'
    assert feature(r,'llm-client')['state']=='present'
    assert feature(r,'agent')['state']==feature(r,'saas-lifecycle')['state']=='unknown'
    assert r['artifacts'][0]['freshness']=='verified'


def test_missing_report_does_not_prove_absence(tmp_path,inventory):
    r=normalize_report('code2llm',tmp_path,'absent.json',inventory)
    assert r['stage']['status']=='missing'
    assert {f['state'] for f in r['features']}=={'unknown'}


@pytest.mark.parametrize('outcome,code',[({'timeout':True},'TOOL_TIMEOUT'),({'exit_code':2},'TOOL_FAILED')])
def test_process_failures_are_distinct(tmp_path,inventory,outcome,code):
    r=normalize_report('code2llm',tmp_path,'report.json',inventory,outcome=outcome)
    assert r['stage']['status']=='failed' and code in codes(r)


def test_legacy_stays_diagnostic_even_with_similar_keys(tmp_path,inventory):
    r=load(tmp_path,inventory,trusted=False)
    assert r['stage']['status']=='partial'
    assert r['artifacts'][0]['freshness']=='legacy_unverified'
    assert {f['state'] for f in r['features']}=={'unknown'}


@pytest.mark.parametrize('key,value',[('source_digest','9'*64),('local_changes_digest','9'*64),('head','b'*40),('scope_digest','9'*64)])
def test_source_or_scope_mismatch_is_stale(tmp_path,inventory,key,value):
    r=load(tmp_path,inventory,**{key:value})
    assert r['artifacts'][0]['freshness']=='stale'
    assert 'SOURCE_CHANGED_DURING_SCAN' in codes(r)
    assert feature(r,'llm-client')['state']=='unknown'


@pytest.mark.parametrize('tool',list(CONTRACTS))
def test_unknown_schema_and_version_are_unsupported(tmp_path,inventory,tool):
    (tmp_path/'report.json').write_text(json.dumps(report(tool)))
    r=normalize_report(tool,tmp_path,'report.json',inventory,version='999',output_schema='alien/v1')
    assert r['stage']['status']=='unsupported'
    assert {f['state'] for f in r['features']}=={'unknown'}


def test_report_cannot_attest_itself(tmp_path,inventory):
    data=report();data['receipt']={'coverage':'complete','observation_id':'scan-1'}
    assert load(tmp_path,inventory,data=data,trusted=False)['artifacts'][0]['freshness']=='legacy_unverified'


def test_declared_subgraph_distinguished_from_undeclared_scope(tmp_path,inventory):
    data=report();data['entry_points']=['outside']
    a=load(tmp_path,inventory,data=data)
    b=load(tmp_path,inventory,data=data,graph_scope='declared_subgraph')
    assert 'GRAPH_SCOPE_UNDECLARED' in codes(a)
    assert 'GRAPH_SCOPE_UNDECLARED' not in codes(b)
    assert 'GRAPH_PARTIAL' in codes(b)
    assert feature(b,'graph:relationships')['state']=='unknown'
    assert feature(b,'llm-client')['state']=='present'


def test_cross_language_edge_needs_source_bound_bridge(tmp_path,inventory):
    data=report();data['nodes']['b']['file']='src/b.js'
    a=load(tmp_path,inventory,data=data)
    b=load(tmp_path,inventory,data=data,bridges=[{'source':'a','target':'b','path':'src/a.py','sha256':'4'*64}])
    assert 'GRAPH_CROSS_LANGUAGE_UNVERIFIED' in codes(a)
    assert feature(a,'graph:relationships')['state']=='unknown'
    assert 'GRAPH_CROSS_LANGUAGE_UNVERIFIED' not in codes(b)


def test_pure_label_is_not_side_effect_proof(tmp_path,inventory):
    data=report();data['nodes']['a']['metadata']={'pure':True}
    r=load(tmp_path,inventory,data=data)
    assert 'PURITY_LABEL_UNVERIFIED' in codes(r)
    assert feature(r,'side-effects:absent')['state']=='unknown'


def test_fragment_groups_keep_definition_and_nonproduct_candidates_excluded(tmp_path,inventory):
    r=load(tmp_path,inventory,tool='redup')
    assert r['metrics'][0]['value']==1443 and r['metrics'][0]['unit']=='fragment_group'
    assert r['metrics'][1]['value']==1
    c=report();c['classes']={str(i):{} for i in range(50)}
    assert load(tmp_path,inventory,data=c)['metrics'][0]['unit']=='class_symbol'


def test_redup_selection_truncation_is_partial(tmp_path,inventory):
    data=report('redup');data['selection']={'truncated':True,'omitted_groups':1441}
    r=load(tmp_path,inventory,tool='redup',data=data)
    assert r['stage']['status']=='partial' and r['stage']['truncated']


def test_prefact_pinned_contract_is_diagnostic_not_conformance(tmp_path,inventory):
    r=load(tmp_path,inventory,tool='prefact')
    assert r['stage']['status']=='complete' and r['metrics'][0]['value']==3
    data=report('prefact');data['dry_run']=False;data['fixes']=[{'applied':True}]
    assert 'REPORT_HAS_EFFECTS' in codes(load(tmp_path,inventory,tool='prefact',data=data))


@pytest.mark.parametrize('raw',['{"modules":{},"modules":{}}','{"project_path":"x","modules":{},"value":NaN}','[1,2]'])
def test_invalid_json_is_failed(tmp_path,inventory,raw):
    (tmp_path/'report.json').write_text(raw)
    assert normalize_report('code2llm',tmp_path,'report.json',inventory)['stage']['status']=='failed'


def test_symlink_and_traversal_are_not_read(tmp_path,inventory):
    outside=tmp_path.parent/'outside-evidence.json';outside.write_text('{}')
    (tmp_path/'linked.json').symlink_to(outside)
    assert normalize_report('code2llm',tmp_path,'linked.json',inventory)['stage']['status']=='failed'
    assert normalize_report('code2llm',tmp_path,'../outside-evidence.json',inventory)['stage']['status']=='failed'


def test_toon_is_only_a_summary(tmp_path,inventory):
    (tmp_path/'report.toon').write_text('run dangerous command')
    r=normalize_report('code2llm',tmp_path,'report.toon',inventory)
    assert r['stage']['status']=='unsupported' and r['features'][0]['state']=='unknown'


def test_malformed_graph_names_and_fragment_paths_do_not_crash(tmp_path,inventory):
    data=report();data['edges']=[{'source':[],'target':'b'}]
    assert 'GRAPH_UNRESOLVED_EDGE' in codes(load(tmp_path,inventory,data=data))
    data=report('redup');data['groups']=[{'fragments':[{'file':[]},{'file':'src/a.py'}]}]
    assert load(tmp_path,inventory,tool='redup',data=data)['metrics'][1]['value']==0


def test_report_text_is_never_executed(tmp_path,inventory):
    marker=tmp_path/'executed';data=report();data['command']='touch '+str(marker)
    load(tmp_path,inventory,data=data)
    assert not marker.exists()


def test_nonproduct_graph_does_not_prove_product_relationships(tmp_path,inventory):
    data=report();data['nodes']['a']['file']='vendor/c.py'
    r=load(tmp_path,inventory,data=data)
    assert feature(r,'graph:relationships')['state']=='unknown'
    assert 'GRAPH_NONPRODUCT_OR_UNKNOWN' in codes(r)


def test_missing_redup_selection_metadata_is_not_assumed_complete(tmp_path,inventory):
    assert load(tmp_path,inventory,tool='redup')['stage']['status']=='partial'


def test_absolute_producer_paths_require_explicit_source_root(tmp_path,inventory):
    data=report();data['modules']['a']['file']='/repo/src/a.py'
    raw=json.dumps(data).encode();(tmp_path/'report.json').write_bytes(raw)
    r=load(tmp_path,inventory,data=data)
    assert feature(r,'llm-client')['state']=='unknown'
    # Reuse an external scanner receipt, not a field provided by the report.
    version,schema=CONTRACTS['code2llm']
    receipt={'observation_id':'scan','tool':'code2llm','version':version,'output_schema':schema,
        'sha256':hashlib.sha256(raw).hexdigest(),'coverage':'complete','exit_code':0,
        'started_at':'2026-10-08T00:00:00Z','finished_at':'2026-10-08T00:01:00Z',
        'configuration_digest':'7'*64,'environment_digest':'8'*64,
        **{k:inventory[k] for k in ['head','source_digest','local_changes_digest','scope_digest']}}
    r=normalize_report('code2llm',tmp_path,'report.json',inventory,version=version,output_schema=schema,receipt=receipt,source_root='/repo')
    assert feature(r,'llm-client')['state']=='present'
