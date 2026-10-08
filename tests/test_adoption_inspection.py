import hashlib
import json
from pathlib import Path

import pytest

from wellman.adoption_inspection import current_adoption, inspect_adoption
from wellman.selection_contracts import payload_digest

ID='wellmanifest/new-project'


def write(root,name,data):
    path=root/'.governance'/name;path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data));return path


def inventory(root, **changes):
    files=[{'path':p.relative_to(root).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in root.rglob('*') if p.is_file() and not p.is_symlink()]
    return {'repository_id':'owner/repo','identity':'confirmed','head':'a'*40,'source_digest':payload_digest(files),
        'local_changes_digest':'2'*64,'complete':True,'files':files,**changes}


@pytest.fixture
def adopted(tmp_path):
    managed=tmp_path/'AGENTS.md';managed.write_text('local instructions')
    write(tmp_path,'manifest.json',{'schema':'new-project.governance/v2','standard':{'id':ID,'version':'1.2.3'},'profile':'baseline'})
    write(tmp_path,'manifest.lock.json',{'schema':'new-project.lock/v1','standard':{'id':ID,'version':'1.2.3','sourceRepository':ID,'sourceRevision':'b'*40,'publicationStatus':'published'},
        'managedFiles':{'AGENTS.md':hashlib.sha256(managed.read_bytes()).hexdigest()}})
    write(tmp_path,'package-manifest.json',{'schema':'new-project.package-manifest/v1','files':[{'target':'AGENTS.md','source':'template/AGENTS.md','strategy':'managed','executable':False}]})
    return tmp_path


def inspect(root,**kwargs):return inspect_adoption(root,inventory=inventory(root),**kwargs)
def codes(result):return {i['code'] for i in result['quality_issues']}


def test_missing_lock_and_profile_are_distinct(tmp_path):
    assert inspect(tmp_path)['standards'][ID]['state']=='missing'
    write(tmp_path,'manifest.json',{'schema':'new-project.governance/v2','standard':{'id':ID,'version':'1.2.3'},'profile':'baseline'})
    r=inspect(tmp_path)
    assert r['standards'][ID]['state']=='declared'
    assert r['standards'][ID]['revision'] is None and not r['standards'][ID]['adopted']


def test_pin_and_matching_hashes_are_not_conformance(adopted):
    r=inspect(adopted);item=r['standards'][ID]
    assert item['state']=='declared' and item['adopted'] and item['revision']=='b'*40
    assert item['conformance']=='unverified' and item['drift']==[]


@pytest.mark.parametrize('data',[{}, {'schema':'alien/v1'}, {'schema':'new-project.lock/v1','managedFiles':{},'standard':{'id':ID}}])
def test_malformed_lock_is_unknown_not_missing(adopted,data):
    write(adopted,'manifest.lock.json',data)
    r=inspect(adopted)
    assert r['standards'][ID]['state']=='unknown'
    assert r['standards']['wellmanifest/agent']['state']=='unknown'


def test_drift_preserved_without_overwrite(adopted):
    path=adopted/'AGENTS.md';path.write_text('my local customization')
    r=inspect(adopted);item=r['standards'][ID]
    assert item['state']=='drifted' and item['drift']==['AGENTS.md']
    assert path.read_text()=='my local customization'


def test_missing_managed_file_is_drift(adopted):
    (adopted/'AGENTS.md').unlink()
    assert inspect(adopted)['standards'][ID]['state']=='drifted'


def test_symlink_target_is_never_read(adopted,tmp_path):
    outside=tmp_path.parent/'outside-governance';outside.write_text('external')
    p=adopted/'AGENTS.md';p.unlink();p.symlink_to(outside)
    r=inspect(adopted)
    assert r['standards'][ID]['state']=='unknown'
    assert 'MANAGED_FILE_UNKNOWN' in codes(r)


def test_bad_requirements_and_unknown_profile_preserve_uncertainty(adopted):
    write(adopted,'standard-requirements.json',{'schema':'wellman.standard-requirements/v1','profiles':['invented'],'requirements':[]})
    assert inspect(adopted)['coverage']=='unknown'
    write(adopted,'standard-requirements.json',{'schema':'wellman.standard-requirements/v1','profiles':[],'requirements':[{'id':'wellmanifest/agent'}]})
    assert 'REQUIREMENTS_UNKNOWN' in codes(inspect(adopted))


def test_declared_requirement_is_not_adoption(adopted):
    write(adopted,'standard-requirements.json',{'schema':'wellman.standard-requirements/v1','profiles':[],'requirements':[{'id':'wellmanifest/agent','minimumLevel':'S4'}]})
    item=inspect(adopted)['standards']['wellmanifest/agent']
    assert item['state']=='declared' and not item['adopted']


def receipt(root):
    inv=inventory(root);r=inspect_adoption(root,inventory=inv)
    return {'schema':'wellman.adoption-validation/v1','standard_id':ID,'revision':'b'*40,
        'outcome':'passed','level':'S4','material_digest':r['material_digest'],'evidence_ref':'receipt:trusted:1',
        **{k:inv[k] for k in ['head','source_digest','local_changes_digest']}}


def test_external_trusted_ledger_required_for_verified_state(adopted):
    attestation=receipt(adopted)
    assert inspect(adopted,validation_receipts=[attestation])['standards'][ID]['conformance']=='unverified'
    r=inspect(adopted,validation_receipts=[attestation],trusted_receipt_digests={payload_digest(attestation)})
    assert r['standards'][ID]['state']=='verified' and r['standards'][ID]['conformance']=='verified'


@pytest.mark.parametrize('key,value',[('head','c'*40),('source_digest','9'*64),('material_digest','9'*64),('revision','c'*40),('level','S0'),('outcome','failed')])
def test_trusted_stale_or_insufficient_receipts_cannot_verify(adopted,key,value):
    attestation=receipt(adopted);attestation[key]=value
    r=inspect(adopted,validation_receipts=[attestation],trusted_receipt_digests={payload_digest(attestation)})
    assert r['standards'][ID]['conformance']=='unverified'


def test_declared_evidence_uri_does_not_grant_trust(adopted):
    write(adopted,'standard-adoption.json',{'schema':'wellmanifest.standard-adoption/v1','mode':'audit','profile':'baseline','repositoryRole':'unclassified',
        'adoptions':[{'id':'wellmanifest/agent','version':'1','revision':'d'*40,'model':'protected-conformance','level':'S4','artifacts':[],
            'evidence':[{'level':'S4','uri':'https://attacker/approved','sha256':'1'*64}]}]})
    item=inspect(adopted)['standards']['wellmanifest/agent']
    assert item['adopted'] and item['conformance']=='unverified'
    assert 'declared:https://attacker/approved' in item['evidence_refs']


def test_pin_conflict_is_unknown(adopted):
    write(adopted,'standard-adoption.json',{'schema':'wellmanifest.standard-adoption/v1','adoptions':[{'id':ID,'version':'1','revision':'d'*40,'model':'protected-conformance','level':'S4','artifacts':[],'evidence':[]}]})
    r=inspect(adopted)
    assert r['standards'][ID]['state']=='unknown' and 'ADOPTION_PIN_CONFLICT' in codes(r)


def test_exceptions_preserved_without_suppressing_drift(adopted):
    path=adopted/'.governance/manifest.json';data=json.loads(path.read_text())
    claim={'standard_id':ID,'scope':'.','expires_at':'2000-01-01T00:00:00Z','reason':'local customization','authority':'self-declared'}
    data['exceptions']=[claim];path.write_text(json.dumps(data));(adopted/'AGENTS.md').write_text('custom')
    r=inspect(adopted);item=r['standards'][ID]
    assert item['state']=='drifted' and item['exceptions']
    assert 'EXCEPTION_AUTHORITY_UNVERIFIED' in codes(r)


def test_digest_binds_adoption_and_observed_managed_bytes(adopted):
    a=inspect(adopted)['adoption_digest'];(adopted/'AGENTS.md').write_text('changed')
    assert inspect(adopted)['adoption_digest']!=a


def test_inspection_never_executes_declared_validators_or_modifies_files(adopted):
    path=adopted/'.governance/manifest.json';data=json.loads(path.read_text());data['validators']=['touch '+str(adopted/'executed')];path.write_text(json.dumps(data))
    before={str(p):p.read_bytes() for p in adopted.rglob('*') if p.is_file()}
    inspect(adopted)
    assert before=={str(p):p.read_bytes() for p in adopted.rglob('*') if p.is_file()}


def test_source_change_during_inspection_prevents_verification(adopted):
    inv=inventory(adopted);attestation=receipt(adopted);(adopted/'AGENTS.md').write_text('changed')
    r=inspect_adoption(adopted,inventory=inv,validation_receipts=[attestation],trusted_receipt_digests={payload_digest(attestation)})
    assert r['coverage']=='unknown' and r['standards'][ID]['conformance']=='unverified'


def test_unknown_repository_identity_cannot_prove_missing_or_verified(adopted):
    r=inspect_adoption(adopted,inventory=inventory(adopted,identity='unconfirmed'))
    assert r['standards'][ID]['state']=='unknown'
    assert r['standards']['wellmanifest/agent']['state']=='unknown'


def test_projection_contains_only_selection_contract_fields(adopted):
    current=current_adoption(inspect(adopted),ID)
    assert set(current)=={'state','revision','manifest_digest','lock_digest','conformance','evidence_refs','exceptions'}


def test_managed_lock_cannot_expand_scope_to_excluded_secrets(adopted,monkeypatch):
    secret=adopted/'.env';secret.write_text('EXCLUDED_TEST_CONTENT')
    path=adopted/'.governance/manifest.lock.json';lock=json.loads(path.read_text());lock['managedFiles']['.env']='9'*64;path.write_text(json.dumps(lock))
    inv=inventory(adopted);inv['files']=[f for f in inv['files'] if f['path']!='.env']
    original=Path.open
    def guarded(self,*args,**kwargs):
        if self==secret:raise AssertionError('Excluded secret must not be read')
        return original(self,*args,**kwargs)
    monkeypatch.setattr(Path,'open',guarded)
    r=inspect_adoption(adopted,inventory=inv)
    assert r['standards'][ID]['state']=='unknown'


def test_conflicting_manifest_and_lock_versions_are_unknown(adopted):
    path=adopted/'.governance/manifest.json';data=json.loads(path.read_text());data['standard']['version']='2.0.0';path.write_text(json.dumps(data))
    assert inspect(adopted)['standards'][ID]['state']=='unknown'
