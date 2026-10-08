from copy import deepcopy

import pytest

from wellman.applicability import BASELINE, RULES, build_catalog, catalog_digest, resolve_applicability
from wellman.registry import STANDARDS_CATALOG
from wellman.selection_contracts import ContractError, payload_digest, validate_document

ID='wellmanifest/new-project';DOCS='wellmanifest/docs';PIN='b'*40


def observation():
    return {'schema':'wellman.observation/v1','observation_id':'scan-1','started_at':'2026-10-08T00:00:00Z',
        'finished_at':'2026-10-08T00:01:00Z','grants_authority':False,
        'repositories':[{'id':'owner/repo','path':'.','head':'a'*40,'identity':'confirmed','source_digest':'1'*64,'local_changes_digest':'2'*64}],
        'components':[{'id':'lib','repository_id':'owner/repo','path':'.','boundary':'confirmed','manifests':['package.json'],'evidence_refs':['inventory']}],
        'scope':{'roots':['.'],'files_digest':'3'*64,'policy_digest':'4'*64,'exclusions':[]},'tools':[],
        'stages':[{'id':'inventory-stage','tool':'inventory','component_id':None,'started_at':'2026-10-08T00:00:00Z',
            'finished_at':'2026-10-08T00:01:00Z','status':'complete','exit_code':0,'truncated':False,'coverage':'complete','errors':[],'artifact_refs':['inventory']}],
        'artifacts':[{'id':'inventory','path':'inventory.json','media_type':'application/json','size_bytes':3,'sha256':'5'*64,'producer':'inventory',
            'origin_observation_id':'scan-1','freshness':'verified'}],
        'features':[{'id':'repository:git','component_id':'lib','state':'present','coverage':'complete','evidence_refs':['inventory'],'reasons':['Confirmed Git identity']}],
        'metrics':[],'quality_issues':[]}


def adoption(**entries):
    records={id:{'state':'missing','revision':None,'manifest_digest':None,'lock_digest':None,'conformance':'unverified','evidence_refs':[],'exceptions':[], 'adopted':False} for id in STANDARDS_CATALOG}
    for id,entry in entries.items():records[id].update(entry)
    result={'schema':'wellman.adoption-inspection/v1','repository_id':'owner/repo','grants_authority':False,'coverage':'complete','standards':records}
    result['adoption_digest']=payload_digest(result);return result


def catalog(ids=(ID,),**metadata):
    defaults={id:{'managed_files':['.governance/'+id.split('/')[1]+'.json'],'validators':['pinned '+id+' conformance check'],'effects':['files']} for id in ids}
    for id,extra in metadata.items():defaults.setdefault(id,{}).update(extra)
    return build_catalog({id:PIN for id in ids},revision='a'*40,trusted_source='wellmanifest/wellman:rules-v1',metadata=defaults)


def choose(result,id=ID,cid='lib'):
    return next(d for d in result['decisions'] if d['standard_id']==id and d['component_id']==cid)


def resolve(obs=None,cat=None,adopt=None,**kwargs):
    obs=deepcopy(obs or observation());adopt=adopt or adoption()
    obs['artifacts'].append({**obs['artifacts'][0],'id':'adoption','path':'adoption.json','producer':'wellman.adoption-inspection','sha256':payload_digest(adopt)})
    obs['stages'].append({**obs['stages'][0],'id':'adoption-stage','tool':'wellman.adoption-inspection','artifact_refs':['adoption'],'status':'complete','coverage':'complete','exit_code':0,'truncated':False})
    return resolve_applicability(obs,cat or catalog(),adopt,**kwargs)


def feature(obs,id,state='present',cid='lib',coverage='complete'):
    obs['features'].append({'id':id,'component_id':cid,'state':state,'coverage':coverage,'evidence_refs':['inventory'],'reasons':['source-bound evidence']})


def test_known_source_and_missing_adoption_yield_add_proposal():
    r=resolve();d=choose(r)
    assert d['applicability']=='applicable' and d['action']=='add'
    assert not r['grants_authority'] and not r['executable']
    assert 'review-concrete-plan' in d['required_authorities']


@pytest.mark.parametrize('conformance',['verified','unverified'])
def test_matching_adoption_is_preserved_with_separate_conformance(conformance):
    a=adoption(**{ID:{'state':'verified' if conformance=='verified' else 'declared','adopted':True,'revision':PIN,'conformance':conformance}})
    d=choose(resolve(adopt=a))
    assert d['action']=='keep'
    assert ('CONFORMANCE_UNVERIFIED' in d['limitations'])==(conformance=='unverified')


def test_declared_profile_without_adoption_does_not_mean_keep():
    assert choose(resolve(adopt=adoption(**{ID:{'state':'declared'}})))['action']=='add'


def test_unknown_lock_and_exception_claims_defer():
    assert choose(resolve(adopt=adoption(**{ID:{'state':'unknown'}})))['action']=='defer'
    assert choose(resolve(adopt=adoption(**{ID:{'state':'declared','exceptions':['self-declared exception']}})))['reasons']==['EXCEPTION_REVIEW_REQUIRED']


def test_drift_requires_review_and_preserves_local_state():
    a=adoption(**{ID:{'state':'drifted','adopted':True,'revision':PIN}})
    d=choose(resolve(adopt=a));assert d['action']=='repair' and d['risk']=='high'
    assert 'LOCAL_CHANGES_MUST_BE_PRESERVED' in d['limitations']


def test_update_requires_declared_migration():
    a=adoption(**{ID:{'state':'declared','adopted':True,'revision':'c'*40}})
    assert choose(resolve(adopt=a))['action']=='defer'
    c=catalog(**{ID:{'migration':{'from_revisions':['c'*40],'description':'Three-way migration to pinned target'}}})
    assert choose(resolve(cat=c,adopt=a))['action']=='update'


def test_drift_cannot_implicitly_upgrade_without_migration():
    a=adoption(**{ID:{'state':'drifted','adopted':True,'revision':'c'*40}})
    assert choose(resolve(adopt=a))['reasons']==['MIGRATION_UNAVAILABLE']


def test_not_applicable_never_removes_adopted_standard():
    obs=observation();feature(obs,'product:published','absent')
    c=catalog((DOCS,),**{DOCS:{'applies_when':{'all':[{'feature':'product:published','is':'present'}],'any':[]}}})
    a=adoption(**{DOCS:{'state':'verified','revision':'c'*40,'conformance':'verified','adopted':True}})
    d=choose(resolve(obs,c,a),DOCS)
    assert d['applicability']=='not_applicable' and d['action']=='keep'
    assert d['current']['revision']=='c'*40


def test_imported_llm_client_does_not_prove_agent_or_saas_or_model_invocation():
    obs=observation();feature(obs,'llm-client')
    c=catalog(('wellmanifest/agent','wellmanifest/saas-lifecycle','wellmanifest/llm'))
    for d in resolve(obs,c)['decisions']:
        if d['standard_id'] in {r['id'] for r in c['standards']}:
            assert d['applicability']=='insufficient_data' and d['action']=='defer'


@pytest.mark.parametrize('freshness',['legacy_unverified','stale'])
def test_legacy_or_stale_evidence_cannot_establish_applicability(freshness):
    obs=observation();obs['artifacts'][0]['freshness']=freshness
    assert choose(resolve(obs))['action']=='defer'


def test_report_failure_cannot_support_negative_evidence():
    obs=observation();feature(obs,'product:published','absent');obs['stages'][0].update(status='failed',exit_code=1,coverage='unknown')
    c=catalog((DOCS,),**{DOCS:{'applies_when':{'all':[{'feature':'product:published','is':'present'}],'any':[]}}})
    assert choose(resolve(obs,c),DOCS)['applicability']=='insufficient_data'


def test_source_change_issue_invalidates_bound_feature():
    obs=observation();obs['quality_issues']=[{'code':'SOURCE_CHANGED_DURING_SCAN','severity':'error','message':'Changed source','affected_refs':['inventory'],'next_action':'Re-scan'}]
    assert choose(resolve(obs))['action']=='defer'


def test_scope_and_feature_budget_fail_closed():
    obs=observation();obs['components'][0]['boundary']='unknown';feature(obs,'runtime:agent-actions')
    d=choose(resolve(obs,catalog(('wellmanifest/agent',))), 'wellmanifest/agent')
    assert d['reasons']==['SCOPE_UNCONFIRMED']
    obs=observation();obs['components']*=201
    with pytest.raises(ContractError):resolve(obs)


def test_repository_scope_deduplicates_shared_standard():
    obs=observation();obs['components'].append({**obs['components'][0],'id':'executor','path':'executor'})
    feature(obs,'repository:git',cid='executor')
    assert len([d for d in resolve(obs)['decisions'] if d['standard_id']==ID])==1


def test_missing_metadata_and_target_revision_defer():
    c=build_catalog({},revision='a'*40,trusted_source='local pinned registry')
    assert choose(resolve(cat=c))['reasons']==['METADATA_MISSING']
    with pytest.raises(ContractError):build_catalog({ID:'main'},revision='a'*40,trusted_source='local')


def test_unknown_catalog_and_advisory_ids_are_rejected_without_effects():
    c=catalog();alien=deepcopy(c['standards'][0]);alien['id']='wellmanifest/invented';c['standards'].append(alien);c['catalog_digest']=catalog_digest(c)
    r=resolve(cat=c,advisory=[{'standard_id':[]},{'standard_id':'wellmanifest/invented'}])
    assert all(d['standard_id'] in STANDARDS_CATALOG for d in r['decisions'])
    assert {'UNKNOWN_STANDARD','ADVISORY_UNKNOWN_STANDARD'}<={d['code'] for d in r['diagnostics']}


def test_advice_failure_and_unknown_ids_do_not_change_decisions():
    baseline=resolve()['decisions']
    assert resolve(advisory={'timeout':True})['decisions']==baseline
    assert resolve(advisory=[{'standard_id':'wellmanifest/invented'}])['decisions']==baseline


def test_dependency_order_and_version_constraints():
    c=catalog((ID,DOCS),**{DOCS:{'depends_on':[{'id':ID,'revisions':[PIN]}]}})
    r=resolve(cat=c)
    assert r['dependency_order'].index(ID)<r['dependency_order'].index(DOCS)
    assert choose(r,DOCS)['action']=='add'
    c['standards'][0]['depends_on'][0]['revisions']=['c'*40]  # docs sorts first
    c['catalog_digest']=catalog_digest(c)
    assert choose(resolve(cat=c),DOCS)['action']=='defer'


def test_cycles_and_unknown_dependency_versions_defer():
    c=catalog((ID,DOCS),**{ID:{'depends_on':[{'id':DOCS,'revisions':[PIN]}]},DOCS:{'depends_on':[{'id':ID,'revisions':[PIN]}]}})
    r=resolve(cat=c)
    assert choose(r)['action']==choose(r,DOCS)['action']=='defer'
    assert 'DEPENDENCY_CYCLE' in {d['code'] for d in r['diagnostics']}
    c=catalog(**{ID:{'depends_on':[{'id':DOCS,'revisions':[PIN]}]}})
    assert choose(resolve(cat=c))['action']=='defer'


def test_conflicts_are_symmetric_even_if_one_catalog_row_declares_them():
    c=catalog((ID,DOCS),**{ID:{'conflicts_with':[DOCS]}})
    r=resolve(cat=c)
    assert choose(r)['action']==choose(r,DOCS)['action']=='defer'
    assert ID in choose(r,DOCS)['conflicts']


def test_deferred_dependency_propagates_to_consumer():
    c=catalog((ID,DOCS),**{ID:{'managed_files':[]},DOCS:{'depends_on':[{'id':ID,'revisions':[PIN]}]}})
    assert choose(resolve(cat=c),DOCS)['action']=='defer'


def test_supersedes_alone_does_not_remove_current_adoption():
    c=catalog(**{ID:{'supersedes':[DOCS]}});a=adoption(**{DOCS:{'state':'declared','revision':'c'*40,'adopted':True}})
    assert choose(resolve(cat=c,adopt=a))['action']=='add'
    obs=observation();feature(obs,'replacement:'+DOCS)
    d=choose(resolve(obs,c,a))
    assert d['action']=='propose_replace' and 'separate-removal-decision' in d['required_authorities']
    assert a['standards'][DOCS]['adopted']


def test_executable_looking_predicate_and_validator_text_are_never_run(tmp_path):
    marker=tmp_path/'executed';c=catalog(**{ID:{'validators':['touch '+str(marker)],'applies_when':{'all':[{'feature':'__import__("os").system("touch '+str(marker)+'")','is':'present'}],'any':[]}}})
    assert choose(resolve(cat=c))['action']=='defer' and not marker.exists()


def test_determinism_and_digest_tampering():
    obs=observation();c=catalog();a=adoption();before=deepcopy((obs,c,a))
    assert resolve(obs,c,a)==resolve(deepcopy(obs),deepcopy(c),deepcopy(a))
    assert (obs,c,a)==before
    c['trusted_source']='changed'
    with pytest.raises(ContractError,match='CATALOG_DIGEST_MISMATCH'):resolve(cat=c)


def test_rule_catalog_covers_real_identifiers_and_decisions_match_contract():
    assert set(RULES)==set(STANDARDS_CATALOG)
    r=resolve();plan={'schema':'wellman.selection-plan/v1','mode':'recommendation','grants_authority':False,'executable':False,
        'observation_id':'scan-1','observation_digest':'1'*64,'catalog_digest':'2'*64,'rule_digest':r['rule_digest'],
        'source_digests':{'owner/repo':'3'*64},'adoption_digests':{'owner/repo':'4'*64},'decisions':r['decisions'],'quality_issues':[]}
    assert validate_document(plan)==plan


def test_unknown_relationship_ids_defer_instead_of_silently_ignoring_constraints():
    c=catalog(**{ID:{'conflicts_with':['wellmanifest/invented']}})
    assert choose(resolve(cat=c))['reasons']==['REFERENCED_STANDARD_UNKNOWN']


def test_effective_rule_override_changes_rule_digest():
    a=resolve()['rule_digest']
    c=catalog(**{ID:{'applies_when':{'all':[{'feature':'product:published','is':'present'}],'any':[]}}})
    assert resolve(cat=c)['rule_digest']!=a


def test_component_capability_does_not_spill_into_other_component():
    obs=observation();obs['components'].append({**obs['components'][0],'id':'executor','path':'executor'})
    feature(obs,'runtime:agent-actions',cid='executor')
    r=resolve(obs,catalog(('wellmanifest/agent',)))
    assert choose(r,'wellmanifest/agent','executor')['action']=='add'
    assert choose(r,'wellmanifest/agent','lib')['action']=='defer'


def test_conflicting_feature_claims_and_dangling_evidence_remain_unknown():
    obs=observation();feature(obs,'repository:git','absent')
    assert choose(resolve(obs))['action']=='defer'
    obs=observation();obs['features'][0]['evidence_refs']=['missing-artifact']
    assert choose(resolve(obs))['action']=='defer'


def test_cached_verified_adoption_requires_a_current_observation_binding():
    a=adoption(**{ID:{'state':'verified','adopted':True,'revision':PIN,'conformance':'verified'}})
    r=resolve_applicability(observation(),catalog(),a)
    d=choose(r)
    assert d['action']=='defer' and d['current']['conformance']=='unverified'
    assert d['reasons']==['ADOPTION_OBSERVATION_UNBOUND']


@pytest.mark.parametrize('executor', ['a-executor', 'z-executor'])
def test_repository_conflict_covers_every_component_regardless_of_anchor(executor):
    agent = 'wellmanifest/agent'
    obs = observation()
    obs['components'].append({**obs['components'][0], 'id': executor, 'path': 'executor'})
    feature(obs, 'runtime:agent-actions', cid=executor)
    c = catalog((ID, agent), **{ID: {'conflicts_with': [agent]}})
    r = resolve(obs, c)
    repository = next(d for d in r['decisions'] if d['standard_id'] == ID)
    assert repository['action'] == 'defer'
    assert repository['conflicts'] == [agent]
    assert choose(r, agent, executor)['action'] == 'defer'
    assert choose(r, agent, executor)['conflicts'] == [ID]


def test_repository_dependency_cannot_ignore_an_unresolved_component():
    agent = 'wellmanifest/agent'
    obs = observation()
    obs['components'].append({**obs['components'][0], 'id': 'z-executor', 'path': 'executor'})
    feature(obs, 'runtime:agent-actions')
    c = catalog((ID, agent), **{ID: {'depends_on': [{'id': agent, 'revisions': [PIN]}]}})
    r = resolve(obs, c)
    assert choose(r, agent)['action'] == 'add'
    assert choose(r, agent, 'z-executor')['action'] == 'defer'
    assert choose(r)['action'] == 'defer'
    assert 'DEPENDENCY_DEFERRED:' + agent in choose(r)['reasons']


def test_component_conflict_does_not_spill_into_sibling_component():
    agent, llm = 'wellmanifest/agent', 'wellmanifest/llm'
    obs = observation()
    obs['components'].append({**obs['components'][0], 'id': 'z-executor', 'path': 'executor'})
    feature(obs, 'runtime:agent-actions')
    feature(obs, 'usage:model-invocation', cid='z-executor')
    c = catalog((agent, llm), **{agent: {'conflicts_with': [llm]}})
    r = resolve(obs, c)
    assert choose(r, agent)['action'] == 'add'
    assert choose(r, agent)['conflicts'] == []
    assert choose(r, llm, 'z-executor')['action'] == 'add'


def test_repository_conflict_does_not_spill_into_other_repository():
    agent = 'wellmanifest/agent'
    obs = observation()
    obs['repositories'].append({**obs['repositories'][0], 'id': 'owner/other', 'path': 'other'})
    obs['components'].append({**obs['components'][0], 'id': 'z-other',
                              'repository_id': 'owner/other', 'path': 'other'})
    feature(obs, 'runtime:agent-actions', cid='z-other')
    c = catalog((ID, agent), **{ID: {'conflicts_with': [agent]}})
    inspections = {'owner/repo': adoption(), 'owner/other': adoption()}
    other = inspections['owner/other']
    other['repository_id'] = 'owner/other'
    other['adoption_digest'] = payload_digest({k: v for k, v in other.items() if k != 'adoption_digest'})
    for index, inspection in enumerate(inspections.values()):
        ref = 'adoption-' + str(index)
        obs['artifacts'].append({**obs['artifacts'][0], 'id': ref, 'path': ref + '.json',
                                'producer': 'wellman.adoption-inspection', 'sha256': payload_digest(inspection)})
        obs['stages'].append({**obs['stages'][0], 'id': ref + '-stage',
                             'tool': 'wellman.adoption-inspection', 'artifact_refs': [ref]})
    r = resolve_applicability(obs, c, inspections)
    assert choose(r)['action'] == 'add'
    assert choose(r)['conflicts'] == []
    assert choose(r, agent, 'z-other')['action'] == 'add'


@pytest.mark.parametrize('current', ['missing', 'update', 'drifted'])
def test_missing_effect_metadata_defers_proposed_changes(current):
    entry = {} if current == 'missing' else {
        ID: {'adopted': True, 'state': 'drifted' if current == 'drifted' else 'declared',
             'revision': PIN if current == 'drifted' else 'c' * 40}}
    c = catalog(**{ID: {'effects': [], 'migration': {
        'from_revisions': ['c' * 40], 'description': 'Explicit reviewed migration'}}})
    d = choose(resolve(cat=c, adopt=adoption(**entry)))
    assert d['action'] == 'defer'
    assert 'EFFECTS_UNKNOWN' in d['reasons']
    assert d['required_authorities'] == []


@pytest.mark.parametrize('path,effect', [
    ('.github/workflows/build.yml', 'ci'),
    ('./.github/workflows/**', 'ci'),
    ('.github', 'ci'),
    ('.github/workflow*/**', 'ci'),
    ('.gitlab-ci.yml', 'ci'),
    ('.circleci/config.yml', 'ci'),
    ('Jenkinsfile', 'ci'),
    ('azure-pipelines.yml', 'ci'),
    ('.travis.yml', 'ci'),
    ('.githooks/pre-push', 'hooks'),
    ('./.githooks/**', 'hooks'),
    ('.git/hooks/pre-commit', 'hooks'),
    ('.pre-commit-config.yaml', 'hooks'),
    ('CODEOWNERS', 'permissions'),
    ('.github/CODEOWNERS', 'permissions'),
    ('.gitlab/CODEOWNERS', 'permissions'),
    ('*', 'ci'),
    ('.', 'hooks'),
])
def test_managed_control_paths_cannot_omit_their_effect(path, effect):
    c = catalog(**{ID: {'managed_files': [path], 'effects': ['files']}})
    d = choose(resolve(cat=c))
    assert d['action'] == 'defer'
    assert 'MANAGED_EFFECT_UNDECLARED:' + effect in d['reasons']
    assert d['required_authorities'] == []


@pytest.mark.parametrize('path,effect', [
    ('.github/workflows/build.yml', 'ci'),
    ('.githooks/pre-push', 'hooks'),
    ('CODEOWNERS', 'permissions'),
])
def test_declared_control_effects_require_explicit_approval(path, effect):
    c = catalog(**{ID: {'managed_files': [path], 'effects': ['files', effect]}})
    d = choose(resolve(cat=c))
    assert d['action'] == 'add' and d['risk'] == 'high'
    assert set(d['required_authorities']) == {'review-concrete-plan', 'approve-declared-effects'}


@pytest.mark.parametrize('path', [
    'docs/guide.md', 'README*.md', '.github/ISSUE_TEMPLATE/bug.md',
    '.github/workflows-example/readme.md', '.githooks-example/readme.md',
])
def test_ordinary_managed_paths_keep_file_proposals(path):
    d = choose(resolve(cat=catalog(**{ID: {'managed_files': [path], 'effects': ['files']}})))
    assert d['action'] == 'add' and d['risk'] == 'medium'
    assert d['required_authorities'] == ['review-concrete-plan']


def test_effect_metadata_gap_preserves_matching_existing_adoption():
    a = adoption(**{ID: {'adopted': True, 'state': 'declared', 'revision': PIN}})
    c = catalog(**{ID: {'managed_files': ['.githooks/pre-push'], 'effects': []}})
    d = choose(resolve(cat=c, adopt=a))
    assert d['action'] == 'keep'
    assert d['current']['revision'] == PIN
    assert d['limitations'] == ['CONFORMANCE_UNVERIFIED']


@pytest.mark.parametrize('path,effects', [
    ('*', ['files', 'ci', 'hooks', 'permissions']),
    ('.github', ['files', 'ci', 'permissions']),
])
def test_broad_scopes_with_complete_effect_declarations_remain_proposals(path, effects):
    d = choose(resolve(cat=catalog(**{ID: {'managed_files': [path], 'effects': effects}})))
    assert d['action'] == 'add' and d['risk'] == 'high'
    assert set(d['required_authorities']) == {'review-concrete-plan', 'approve-declared-effects'}


@pytest.mark.parametrize('update', [{'errors': ['producer error']},
                                    {'status': 'failed'}, {'coverage': 'partial'}])
def test_invalid_complete_feature_stage_cannot_propose_standard_change(update):
    obs = observation()
    obs['stages'][0].update(update)
    d = choose(resolve(obs))
    assert d['applicability'] == 'insufficient_data' and d['action'] == 'defer'


@pytest.mark.parametrize('affected', [[], ['inventory-stage'], ['inventory'], ['lib'], ['owner/repo']])
def test_scoped_quality_error_invalidates_standard_evidence(affected):
    obs = observation()
    obs['quality_issues'].append({'code': 'GRAPH_INVALID', 'severity': 'error',
        'message': 'Invalid inventory evidence', 'affected_refs': affected, 'next_action': 'rescan'})
    d = choose(resolve(obs))
    assert d['applicability'] == 'insufficient_data' and d['action'] == 'defer'


@pytest.mark.parametrize('update', [{'status': 'failed', 'exit_code': 1}, {'errors': ['inspection failed']},
                                    {'status': 'partial', 'truncated': True}, {'coverage': 'partial'}])
def test_invalid_adoption_stage_cannot_propose_adoption(update):
    obs = observation()
    a = adoption()
    obs['artifacts'].append({**obs['artifacts'][0], 'id': 'adoption', 'path': 'adoption.json',
        'producer': 'wellman.adoption-inspection', 'sha256': payload_digest(a)})
    obs['stages'].append({**obs['stages'][0], 'id': 'adoption-stage',
        'tool': 'wellman.adoption-inspection', 'artifact_refs': ['adoption'], **update})
    d = choose(resolve_applicability(obs, catalog(), a))
    assert d['action'] == 'defer' and d['reasons'] == ['ADOPTION_OBSERVATION_UNBOUND']


def test_quality_error_on_adoption_stage_does_not_certify_missing_adoption():
    obs = observation()
    obs['quality_issues'].append({'code': 'INSPECTION_INVALID', 'severity': 'error',
        'message': 'Invalid adoption stage', 'affected_refs': ['adoption-stage'], 'next_action': 'rescan'})
    d = choose(resolve(obs))
    assert d['applicability'] == 'applicable'
    assert d['action'] == 'defer' and d['reasons'] == ['ADOPTION_OBSERVATION_UNBOUND']


def test_partial_success_retains_positive_evidence_but_not_complete_or_absent_proof():
    obs = observation()
    obs['stages'][0].update(status='partial', coverage='partial', truncated=True)
    c = catalog(**{ID: {'requires_evidence': []}})
    assert choose(resolve(obs, c))['action'] == 'add'
    obs['features'][0]['state'] = 'absent'
    assert choose(resolve(obs, c))['applicability'] == 'insufficient_data'


def test_unrelated_quality_error_preserves_standard_proposal():
    obs = observation()
    obs['quality_issues'].append({'code': 'OTHER_STAGE_FAILED', 'severity': 'error',
        'message': 'Unrelated error', 'affected_refs': ['other-stage'], 'next_action': 'rescan'})
    assert choose(resolve(obs))['action'] == 'add'


def test_duplicate_producing_stage_ids_defer_instead_of_choosing_a_proof():
    obs = observation()
    obs['stages'].append(deepcopy(obs['stages'][0]))
    assert choose(resolve(obs))['action'] == 'defer'


@pytest.mark.parametrize('update', [{'exit_code': 1}, {'errors': ['partial producer failed']}])
def test_partial_failure_cannot_establish_positive_capability(update):
    obs = observation()
    obs['stages'][0].update(status='partial', coverage='partial', **update)
    c = catalog(**{ID: {'requires_evidence': []}})
    assert choose(resolve(obs, c))['applicability'] == 'insufficient_data'


@pytest.mark.parametrize('update', [{'exit_code': 1}, {'truncated': True}])
def test_existing_contract_rejection_for_inconsistent_complete_stage_is_preserved(update):
    obs = observation()
    obs['stages'][0].update(update)
    with pytest.raises(ContractError, match='complete stage'):
        resolve(obs)
