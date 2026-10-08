"""Inspect governance adoption without changing pins or executing validators.

Trusted receipt digests must come from an independently verified authority
ledger supplied by the caller. They are never loaded from project declarations.
A matching hash alone does not establish that ledger's trust.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath

from wellman.adoption import expand_profiles
from wellman.components import _safe, inventory_repository
from wellman.evidence import _json
from wellman.registry import PROFILES_CATALOG, STANDARDS_CATALOG
from wellman.selection_contracts import (
    MAX_DOCUMENT_BYTES,
    ContractError,
    canonical_bytes,
    payload_digest,
)

DOCUMENTS = {
    'manifest.json':'new-project.governance/v2',
    'manifest.lock.json':'new-project.lock/v1',
    'package-manifest.json':'new-project.package-manifest/v1',
    'standard-requirements.json':'wellman.standard-requirements/v1',
    'standard-adoption.json':'wellmanifest.standard-adoption/v1',
}
CURRENT_FIELDS = ('state','revision','manifest_digest','lock_digest','conformance','evidence_refs','exceptions')
EXTENDABLE_PAIRS = {
    ('governance/manifest.default.json', '.governance/manifest.json'),
    ('governance/ticket-allocation.json', '.governance/ticket-allocation.json'),
    ('governance/required-checks.json', '.governance/required-checks.json'),
    ('template/files/required-checks.template.json', '.governance/required-checks.json'),
}


def _digest(root, relative):
    target = _safe(root, relative)
    if not target.exists():
        return None, None
    if not target.is_file():
        raise ContractError('Evidence must be a regular file')
    before=target.stat()
    with target.open('rb') as handle:
        raw=handle.read(MAX_DOCUMENT_BYTES+1)
    after=target.stat()
    if len(raw)>MAX_DOCUMENT_BYTES or (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise ContractError('Evidence changed or exceeded the byte budget')
    return raw, hashlib.sha256(raw).hexdigest()


def _revision(value):return isinstance(value,str) and re.fullmatch('[0-9a-f]{40}([0-9a-f]{24})?',value) is not None

def _managed(value):
    if not isinstance(value,dict) or not value:
        raise ContractError('Managed digests must be a nonempty object')
    for path,digest in value.items():
        if not isinstance(path,str) or not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):
            raise ContractError('Invalid managed file digest')
    return value


def inspect_adoption(root, *, inventory=None, validation_receipts=(), trusted_receipt_digests=()):
    root=Path(root).absolute()
    if any(p.is_symlink() for p in (root,*root.parents)):
        raise ContractError('Adoption root must not traverse a symlink')
    inventory=inventory_repository(root) if inventory is None else inventory
    files={f['path']:f.get('sha256') for f in inventory['files']}
    documents,issues,records,managed_observation,extension_observation = {},[],{},{},{}
    def issue(code, path):issues.append({'code':code,'path':path})
    for name,schema in DOCUMENTS.items():
        relative='.governance/'+name
        document={'path':relative,'status':'missing','sha256':None,'data':None}
        try:
            raw,digest=_digest(root,relative);document['sha256']=digest
            if raw is not None:
                data=_json(raw)
                if data.get('schema')!=schema:
                    raise ContractError('Unknown adoption document schema')
                if name=='manifest.json' and (not isinstance(data.get('standard'),dict) or data['standard'].get('id')!='wellmanifest/new-project' or not isinstance(data['standard'].get('version'),str) or not re.fullmatch('[0-9]+\\.[0-9]+\\.[0-9]+',data['standard']['version'])):
                    raise ContractError('Malformed governance manifest identity')
                document.update(status='complete',data=data)
                if files.get(relative)!=digest:
                    issue('SOURCE_CHANGED_DURING_INSPECTION',relative)
        except (OSError,ValueError,RecursionError):
            document['status']='unknown';issue('ADOPTION_DOCUMENT_UNKNOWN',relative)
        documents[name]=document
    unknown=any(d['status']=='unknown' for d in documents.values())
    def record(identifier):
        if identifier not in records:
            records[identifier]={'state':'unknown' if unknown or inventory['identity']!='confirmed' else 'missing',
                'revision':None,'manifest_digest':documents['manifest.json']['sha256'],
                'lock_digest':documents['manifest.lock.json']['sha256'],'conformance':'unverified',
                'evidence_refs':[],'exceptions':[],'adopted':False,'managed_files':[],
                'minimum_level':STANDARDS_CATALOG[identifier].minimum_level if identifier in STANDARDS_CATALOG else 'S0',
                'drift':[]}
        return records[identifier]
    # Missing entries are meaningful only after known documents have been inspected.
    for identifier in sorted(STANDARDS_CATALOG):record(identifier)
    def declare(identifier, ref, level=None):
        if not isinstance(identifier,str) or not re.fullmatch('wellmanifest/[a-z0-9]+(-[a-z0-9]+)*',identifier):
            raise ContractError('Invalid standard identifier')
        item=record(identifier);item['evidence_refs'].append(ref)
        if identifier not in STANDARDS_CATALOG:
            item['state']='unknown';issue('UNKNOWN_STANDARD',ref)
        elif item['state']=='missing':item['state']='declared'
        if level is not None:
            if not isinstance(level,str) or level not in {f'S{i}' for i in range(6)}:
                raise ContractError('Invalid conformance level')
            item['minimum_level']=max(item['minimum_level'],level)
        return item
    def managed(item, expected, ref):
        for relative,digest in sorted(expected.items()):
            observed=None
            try:
                target=_safe(root,relative)
                if relative not in files and target.exists():
                    raise ContractError('Managed file lies outside observed inventory scope')
                _,observed=_digest(root,relative)
                if relative in files and files[relative]!=observed:
                    issue('SOURCE_CHANGED_DURING_INSPECTION',relative)
            except (OSError,ValueError):
                item['state']='unknown';issue('MANAGED_FILE_UNKNOWN',relative)
            managed_observation[relative]={'expected':digest,'observed':observed}
            item['managed_files'].append({'path':relative,'expected':digest,'observed':observed})
            if observed!=digest:
                item['drift'].append(relative)
                if item['state']!='unknown':item['state']='drifted'
        item['evidence_refs'].append(ref)
    profiles=set()
    for name in ('manifest.json','standard-adoption.json'):
        data=documents[name]['data'] or {}
        for key in ('profile','repositoryRole'):
            value=data.get(key)
            if isinstance(value,str) and value in PROFILES_CATALOG:
                profiles.add(value)
            elif key=='profile' and value is not None:
                documents[name]['status']='unknown';issue('UNKNOWN_PROFILE',documents[name]['path'])
        exceptions=data.get('exceptions',[])
        if isinstance(exceptions,list):
            # Retain claims, without granting validity or hiding drift.
            for claim in exceptions:
                if isinstance(claim,dict) and isinstance(claim.get('standard_id'),str):
                    record(claim['standard_id'])['exceptions'].append(canonical_bytes(claim).decode())
                    issue('EXCEPTION_AUTHORITY_UNVERIFIED',documents[name]['path'])
    req=documents['standard-requirements.json']
    if req['data'] is not None:
        try:
            data=req['data'];items=data.get('requirements');declared=data.get('profiles')
            if not isinstance(items,list) or not isinstance(declared,list) or any(not isinstance(p,str) or p not in PROFILES_CATALOG for p in declared):
                raise ContractError('Malformed requirements')
            seen=set()
            for item in items:
                if not isinstance(item,dict) or not isinstance(item.get('id'),str) or item['id'] in seen:
                    raise ContractError('Duplicate or malformed requirement')
                if 'minimumLevel' not in item:raise ContractError('Requirement level missing')
                declare(item['id'],req['path'],item['minimumLevel']);seen.add(item['id'])
            profiles.update(declared)
        except (ValueError,TypeError):
            req['status']='unknown';issue('REQUIREMENTS_UNKNOWN',req['path'])
    for identifier,level in expand_profiles(sorted(profiles)).items():
        declare(identifier,'profile:'+','.join(sorted(profiles)),level)
    lock=documents['manifest.lock.json']
    if lock['data'] is not None:
        try:
            data=lock['data'];standard=data.get('standard')
            if set(data)!={'schema','standard','managedFiles'} or not isinstance(standard,dict) or standard.get('id')!='wellmanifest/new-project' or not _revision(standard.get('sourceRevision')) or standard.get('sourceRepository')!='wellmanifest/new-project' or standard.get('publicationStatus') not in ('published','unpublished-test') or not isinstance(standard.get('version'),str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',standard['version']):
                raise ContractError('Malformed lock identity')
            manifest=documents['manifest.json']['data']
            if manifest is not None and manifest['standard']['version']!=standard['version']:
                raise ContractError('Manifest and lock version conflict')
            expected=_managed(data.get('managedFiles'))
            item=declare(standard['id'],lock['path']);item.update(adopted=True,revision=standard['sourceRevision'])
            managed(item,expected,lock['path'])
            if standard['publicationStatus']!='published':
                item['state']='unknown';issue('PIN_UNPUBLISHED',lock['path'])
        except (ValueError,TypeError):
            lock['status']='unknown';record('wellmanifest/new-project')['state']='unknown';issue('ADOPTION_LOCK_UNKNOWN',lock['path'])
    adoption=documents['standard-adoption.json']
    if adoption['data'] is not None:
        try:
            items=adoption['data'].get('adoptions')
            if not isinstance(items,list):raise ContractError('Malformed adoption list')
            seen=set()
            for entry in items:
                if not isinstance(entry,dict) or not isinstance(entry.get('id'),str) or entry['id'] in seen or not _revision(entry.get('revision')) or not isinstance(entry.get('artifacts'),list) or not isinstance(entry.get('evidence'),list):
                    raise ContractError('Malformed or duplicate adoption')
                if not {'id','version','revision','model','level','artifacts','evidence'}<=entry.keys() or not isinstance(entry['version'],str) or not entry['version'] or entry['model'] not in ('reference-only','local-conformance','protected-conformance','runtime-conformance'):
                    raise ContractError('Incomplete adoption identity')
                item=declare(entry['id'],adoption['path'],entry['level']);seen.add(entry['id'])
                if item['revision'] is not None and item['revision']!=entry['revision']:
                    item['state']='unknown';issue('ADOPTION_PIN_CONFLICT',adoption['path']);continue
                item.update(adopted=True,revision=entry['revision'])
                expected={}
                for artifact in entry['artifacts']:
                    if not isinstance(artifact,dict) or not isinstance(artifact.get('target'),str) or artifact['target'] in expected:
                        raise ContractError('Malformed artifact')
                    expected[artifact['target']]=artifact.get('sha256')
                if expected:managed(item,_managed(expected),adoption['path'])
                # Declared evidence URIs are pointers, never verification outcomes.
                item['evidence_refs']+=['declared:'+e['uri'] for e in entry['evidence'] if isinstance(e,dict) and isinstance(e.get('uri'),str)]
        except (ValueError,TypeError):
            adoption['status']='unknown';issue('ADOPTION_LIST_UNKNOWN',adoption['path'])
    package=documents['package-manifest.json']
    if package['data'] is not None:
        try:
            entries=package['data'].get('files')
            if set(package['data'])!={'schema','files'} or not isinstance(entries,list):
                raise ContractError('Malformed package map')
            targets=set()
            for entry in entries:
                if not isinstance(entry,dict) or set(entry)!={'source','target','strategy','executable'} or entry.get('strategy') not in ('managed','seed','extendable') or type(entry.get('executable')) is not bool:
                    raise ContractError('Malformed package entry')
                for value in (entry['source'],entry['target']):
                    if not isinstance(value,str) or not value or PurePosixPath(value).is_absolute() or '..' in PurePosixPath(value).parts or '\\' in value:
                        raise ContractError('Unsafe package path')
                if entry['target'] in targets:
                    raise ContractError('Duplicate package target')
                _safe(root,entry['target']);targets.add(entry['target'])
                if entry['strategy']=='managed' and entry['target'] not in managed_observation:
                    issue('PACKAGE_TARGET_UNBOUND',entry['target'])
                if entry['strategy']=='extendable':
                    if (entry['source'],entry['target']) not in EXTENDABLE_PAIRS or entry['executable']:
                        raise ContractError('Unauthorized package extension')
                    if entry['target']=='.governance/manifest.json' and not any(isinstance(base,dict) and base.get('target')=='.governance/manifest.base.json' and base.get('strategy')=='managed' and base.get('source')==entry['source'] for base in entries):
                        raise ContractError('Manifest extension requires matching managed base')
                    # Instance bytes are local customizations, not a template pin.
                    # Bind them to inspection/receipts without expanding scan scope.
                    if files.get(entry['target']) is None:
                        issue('PACKAGE_TARGET_UNBOUND',entry['target']);continue
                    _,digest=_digest(root,entry['target'])
                    extension_observation[entry['target']]=digest
                    if digest!=files[entry['target']]:
                        issue('SOURCE_CHANGED_DURING_INSPECTION',entry['target'])
        except (OSError,ValueError,TypeError):
            package['status']='unknown';issue('PACKAGE_MAP_UNKNOWN',package['path'])
    material={'documents':{name:{k:d[k] for k in ('status','sha256')} for name,d in documents.items()},
              'managed':managed_observation,'repository_id':inventory['repository_id']}
    if extension_observation:material['extensions']=extension_observation
    material_digest=payload_digest(material)
    safe_coverage=not any(d['status']=='unknown' for d in documents.values()) and inventory['identity']=='confirmed'
    unchanged=not any(i['code']=='SOURCE_CHANGED_DURING_INSPECTION' for i in issues)
    for identifier,item in records.items():
        if not safe_coverage and item['state'] in ('missing','declared'):
            item['state']='unknown'
        required_documents = ('manifest.json','manifest.lock.json','package-manifest.json') if identifier=='wellmanifest/new-project' else ('standard-adoption.json',)
        if item['state']=='declared' and item['adopted'] and not item['drift'] and safe_coverage and unchanged and inventory['complete'] and all(documents[n]['status']=='complete' for n in required_documents) and not any(i['code']=='PACKAGE_TARGET_UNBOUND' for i in issues):
            for receipt in validation_receipts:
                if not isinstance(receipt,dict) or payload_digest(receipt) not in trusted_receipt_digests:continue
                if receipt.get('schema')!='wellman.adoption-validation/v1' or receipt.get('outcome')!='passed' or receipt.get('standard_id')!=identifier or receipt.get('revision')!=item['revision'] or receipt.get('material_digest')!=material_digest or not isinstance(receipt.get('level'),str) or receipt['level']<item['minimum_level'] or receipt['level'] not in {f'S{i}' for i in range(6)} or not isinstance(receipt.get('evidence_ref'),str) or not receipt['evidence_ref']:
                    continue
                if any(receipt.get(k)!=inventory[k] for k in ('head','source_digest','local_changes_digest')):continue
                item.update(state='verified',conformance='verified');item['evidence_refs'].append(receipt['evidence_ref'])
        item['evidence_refs']=sorted(set(item['evidence_refs']));item['exceptions']=sorted(set(item['exceptions']))
    result={'schema':'wellman.adoption-inspection/v1','grants_authority':False,
            'repository_id':inventory['repository_id'],'coverage':'complete' if safe_coverage and unchanged else 'unknown',
            'documents':material['documents'],'material_digest':material_digest,'standards':dict(sorted(records.items())),
            'quality_issues':issues,'profiles':sorted(profiles)}
    result['adoption_digest']=payload_digest(result)
    return result


def current_adoption(inspection, identifier):
    """Project a record to the selection-plan adoption contract."""
    if identifier in inspection['standards']:
        return {key:inspection['standards'][identifier][key] for key in CURRENT_FIELDS}
    return {'state':'unknown','revision':None,'manifest_digest':None,'lock_digest':None,
            'conformance':'unverified','evidence_refs':[],'exceptions':[]}
