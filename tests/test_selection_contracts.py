import copy
import json
from pathlib import Path

import pytest

from wellman.selection_contracts import (
    ContractError, canonical_bytes, payload_digest, plan_digest, validate_document,
)


def observation():
    return {
        'schema':'wellman.observation/v1','observation_id':'scan-1',
        'started_at':'2026-10-08T08:00:00Z','finished_at':'2026-10-08T08:01:00Z',
        'grants_authority':False,'repositories':[],'components':[],
        'scope':{'roots':['.'],'files_digest':'a'*64,'policy_digest':'b'*64,'exclusions':[]},
        'tools':[],'stages':[],'artifacts':[],'features':[],'metrics':[],'quality_issues':[],
    }


def stage(status='complete'):
    return {'id':'stage-1','tool':'code2llm','component_id':None,
            'started_at':'2026-10-08T08:00:00Z','finished_at':'2026-10-08T08:01:00Z',
            'status':status,'exit_code':0 if status=='complete' else None,
            'truncated':False,'coverage':'complete' if status=='complete' else 'unknown',
            'errors':[],'artifact_refs':[]}


def plan():
    return {'schema':'wellman.selection-plan/v1','mode':'recommendation','grants_authority':False,
            'executable':False,'observation_id':'scan-1','observation_digest':'a'*64,
            'catalog_digest':'b'*64,'rule_digest':'c'*64,'source_digests':{'repo':'d'*64},
            'adoption_digests':{'repo':'e'*64},'decisions':[],'quality_issues':[]}


def test_contracts_are_bundled_valid_json_schema():
    from wellman.selection_contracts import SCHEMAS
    for name in SCHEMAS.values():
        schema=json.loads((Path(__import__('wellman.selection_contracts',fromlist=['x']).__file__).parent/'schemas'/name).read_text())
        assert schema['$schema']=='https://json-schema.org/draft/2020-12/schema'
        assert schema['additionalProperties'] is False


@pytest.mark.parametrize('status',['complete','partial','failed','missing','unsupported'])
def test_report_states_are_explicit_and_preserved(status):
    doc=observation(); doc['stages']=[stage(status)]
    assert validate_document(doc)['stages'][0]['status']==status


@pytest.mark.parametrize('state',['present','absent','unknown'])
def test_feature_states_are_separate_from_report_status(state):
    doc=observation();doc['features']=[{'id':'llm','component_id':'lib','state':state,
        'coverage':'complete' if state!='unknown' else 'unknown','evidence_refs':['stage-1'] if state!='unknown' else [],'reasons':[]}]
    assert validate_document(doc)['features'][0]['state']==state


@pytest.mark.parametrize('coverage',['partial','unknown'])
def test_no_negative_feature_from_incomplete_evidence(coverage):
    doc=observation();doc['features']=[{'id':'agent','component_id':'lib','state':'absent',
        'coverage':coverage,'evidence_refs':['stage-1'],'reasons':[]}]
    with pytest.raises(ContractError,match='complete coverage'): validate_document(doc)


@pytest.mark.parametrize('key,value',[('truncated',True),('exit_code',1),('exit_code',None)])
def test_failed_or_truncated_stage_cannot_claim_complete(key,value):
    doc=observation(); doc['stages']=[{**stage(),key:value}]
    with pytest.raises(ContractError): validate_document(doc)


@pytest.mark.parametrize('key,value',[('grants_authority',True),('executable',True),('mode','apply'),('schema','unknown/v1'),('source_digests',{'r':'main'})])
def test_plan_rejects_authority_and_unpinned_inputs(key,value):
    with pytest.raises(ContractError): validate_document({**plan(),key:value})


def test_missing_and_unknown_fields_fail_closed():
    doc=observation();del doc['artifacts']
    with pytest.raises(ContractError,match='missing'): validate_document(doc)
    with pytest.raises(ContractError,match='unknown properties'): validate_document({**plan(),'apply_command':'touch pwned'})


def test_catalog_requires_pinned_revision():
    doc={'schema':'wellman.applicability-catalog/v1','revision':'a'*40,'catalog_digest':'b'*64,
         'rule_version':'1','trusted_source':'wellmanifest','standards':[]}
    assert validate_document(doc)==doc
    with pytest.raises(ContractError): validate_document({**doc,'revision':'main'})


def test_digest_is_stable_and_binds_material_inputs():
    doc=plan(); old=plan_digest(doc)
    assert old==plan_digest(dict(reversed(list(doc.items()))))
    assert old==plan_digest({**doc,'plan_hash':old,'rendered_at':'2026-10-08T08:02:00Z','output_path':'plan.json'})
    for key in ['observation_id','observation_digest','catalog_digest','rule_digest','source_digests','adoption_digests']:
        changed=copy.deepcopy(doc)
        changed[key]='next-scan' if key=='observation_id' else ({'repo':'f'*64} if isinstance(changed[key],dict) else 'f'*64)
        assert old!=plan_digest(changed),key
    assert payload_digest(['a','b'])!=payload_digest(['b','a'])


@pytest.mark.parametrize('invalid',[float('nan'),float('inf'),{1:'value'},('tuple',),object()])
def test_canonical_json_does_not_coerce_unrepresentable_values(invalid):
    with pytest.raises(ContractError): canonical_bytes(invalid)


def test_boolean_is_not_a_numeric_exit_code():
    doc=observation(); doc['stages']=[{**stage(),'exit_code':False}]
    with pytest.raises(ContractError): validate_document(doc)


def test_nested_evidence_is_bounded():
    doc={}
    for _ in range(70): doc={'nested':doc}
    with pytest.raises(ContractError,match='nesting'):canonical_bytes(doc)


def test_validation_has_no_external_effects(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert validate_document(plan())['executable'] is False
    assert list(tmp_path.iterdir())==[]


@pytest.mark.parametrize('schema',[None,[],{},False,1])
def test_malformed_schema_identifier_is_a_contract_error(schema):
    with pytest.raises(ContractError,match='Unknown'): validate_document({'schema':schema})


@pytest.mark.parametrize('state',['present','absent'])
def test_known_feature_requires_an_evidence_reference(state):
    doc=observation();doc['features']=[{'id':'agent','component_id':'lib','state':state,
        'coverage':'complete','evidence_refs':[],'reasons':[]}]
    with pytest.raises(ContractError,match='evidence references'):validate_document(doc)
