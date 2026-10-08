"""Deterministic, declarative applicability and proposal resolution.

The versioned rules identify candidates, not permission. Target revisions and
managed projections are supplied by a pinned catalog; missing target metadata
is explicit. Advice never changes facts, rules, decisions or authority.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from fnmatch import fnmatchcase
from pathlib import PurePosixPath
import re

from wellman.adoption_inspection import current_adoption
from wellman.registry import PROFILES_CATALOG, STANDARDS_CATALOG
from wellman.selection_contracts import ContractError, payload_digest, validate_document
from wellman.observation_evidence import ObservationEvidence

RULE_VERSION = 'wellman.applicability-rules/v1'
BASELINE = {r['id'] for r in PROFILES_CATALOG['baseline'].requirements}
# Evidence names describe capabilities. Imports/names are not autonomous actions.
CAPABILITIES = {
    'authority-lifecycle':'runtime:effectful-execution','poa':'runtime:effectful-execution',
    'llm':'usage:model-invocation','dsl':'contract:dsl','code-dsl':'contract:code-dsl',
    'nl-dsl-llm':'usage:nl-to-dsl','nl-api-llm':'usage:nl-to-api',
    'nohardcode':'quality:configuration-audit', 'taskand':'contract:uri-capsule',
    'uriprocess':'contract:uri-process-package', 'nl-uri-dsl-llm':'usage:nl-to-uri',
    'repair-lifecycle':'runtime:automatic-repair','deployment':'lifecycle:deployment',
    'agent':'runtime:agent-actions','policy-dsl':'contract:policy-dsl','skills':'runtime:skills',
    'account-runtime':'runtime:accounts','saas-lifecycle':'lifecycle:subscriptions',
    'twin-lifecycle':'lifecycle:digital-twin','anonym':'data:identifying-information',
    'legal-lifecycle':'product:published','product-lifecycle':'product:published',
}
RULES = {identifier:{'scope':'repository' if identifier in BASELINE else 'component',
    'applies_when':{'all':[{'feature':'repository:git' if identifier in BASELINE else CAPABILITIES[identifier.split('/')[1]],'is':'present'}],'any':[]},
    'requires_evidence':['complete:'+('repository:git' if identifier in BASELINE else CAPABILITIES[identifier.split('/')[1]])]}
    for identifier in STANDARDS_CATALOG}


def catalog_digest(catalog):
    return payload_digest({k:v for k,v in catalog.items() if k!='catalog_digest'})


def build_catalog(pins, *, revision, trusted_source, metadata=None):
    """Bind versioned candidate rules to explicitly supplied immutable targets.

    Unpinned standards stay in the registry and receive METADATA_MISSING during
    resolution. Empty scopes/validators or missing effect declarations cannot
    yield a change proposal.
    This function performs no remote lookup and invents no target revisions.
    """
    metadata=metadata or {};standards=[]
    if set(pins)-STANDARDS_CATALOG.keys() or set(metadata)-STANDARDS_CATALOG.keys():
        raise ContractError('UNKNOWN_STANDARD')
    for identifier,pin in sorted(pins.items()):
        rule=deepcopy(RULES[identifier]);extra=deepcopy(metadata.get(identifier,{}))
        row={'id':identifier,'revision':pin,**rule,'depends_on':[], 'conflicts_with':[],
             'supersedes':[],'managed_files':[],'validators':[],
             'migration':{'from_revisions':[],'description':'No migration declared.'},'effects':[],**extra}
        if row['id']!=identifier or row['revision']!=pin:
            raise ContractError('Metadata must not redirect a target pin')
        standards.append(row)
    catalog={'schema':'wellman.applicability-catalog/v1','revision':revision,'catalog_digest':'0'*64,
             'rule_version':RULE_VERSION,'trusted_source':trusted_source,'standards':standards}
    catalog['catalog_digest']=catalog_digest(catalog);validate_document(catalog)
    return catalog


def _combine(values, operator):
    if operator=='all':
        return False if False in values else None if None in values else True
    return True if True in values else None if None in values else False


def _managed_control_effects(paths):
    """Minimum effects evident from managed control paths, never a full audit.

    Directory and overlapping glob scopes can include control files. Unknown
    runtime effects still require explicit catalog metadata and concrete review.
    No file is read, validator executed or authority granted by this check.
    """
    directories = {
        '.github/workflows': 'ci', '.circleci': 'ci',
        '.githooks': 'hooks', '.git/hooks': 'hooks',
    }
    files = {
        '.gitlab-ci.yml': 'ci', 'Jenkinsfile': 'ci',
        'azure-pipelines.yml': 'ci', '.travis.yml': 'ci',
        '.pre-commit-config.yaml': 'hooks',
        'CODEOWNERS': 'permissions', '.github/CODEOWNERS': 'permissions',
        '.gitlab/CODEOWNERS': 'permissions',
    }
    effects = set()
    for pattern in paths:
        path = str(PurePosixPath(pattern))
        if path == '.':
            effects.update(directories.values())
            effects.update(files.values())
            continue
        prefix = re.split(r'[*?\[]', path, maxsplit=1)[0]
        glob = prefix != path
        for root, effect in directories.items():
            if (glob and (root.startswith(prefix) or prefix.startswith(root + '/'))
                    or not glob and (path == root or path.startswith(root + '/')
                                     or root.startswith(path + '/'))):
                effects.add(effect)
        for root, effect in files.items():
            if fnmatchcase(root, path) or not glob and root.startswith(path + '/'):
                effects.add(effect)
    return effects


def resolve_applicability(observation, catalog, adoptions, *, advisory=None):
    """Resolve outcomes without effects. Inspections require a fresh, hash-bound
    adoption artifact/stage in this observation; cached conformance is not reused.
    """
    validate_document(observation);validate_document(catalog)
    if catalog['catalog_digest']!=catalog_digest(catalog):raise ContractError('CATALOG_DIGEST_MISMATCH')
    if catalog['rule_version']!=RULE_VERSION:raise ContractError('RULE_VERSION_UNSUPPORTED')
    if len(observation['components'])>200:raise ContractError('Component budget exceeded')
    diagnostics=[];metadata={}
    for row in catalog['standards']:
        if row['id'] not in STANDARDS_CATALOG:
            diagnostics.append({'code':'UNKNOWN_STANDARD','standard_id':row['id']});continue
        if row['id'] in metadata:raise ContractError('Duplicate standard metadata')
        metadata[row['id']]=row
    repositories={r['id']:r for r in observation['repositories']}
    components={c['id']:c for c in observation['components']}
    artifacts={a['id']:a for a in observation['artifacts']}
    if len(repositories)!=len(observation['repositories']) or len(components)!=len(observation['components']) or len(artifacts)!=len(observation['artifacts']):
        raise ContractError('AMBIGUOUS_OBSERVATION')
    if any(c['repository_id'] not in repositories for c in components.values()):raise ContractError('COMPONENT_REPOSITORY_UNKNOWN')
    if any(f['component_id'] not in components for f in observation['features']):raise ContractError('FEATURE_COMPONENT_UNKNOWN')
    if adoptions.get('schema')=='wellman.adoption-inspection/v1':adoptions={adoptions['repository_id']:adoptions}
    for repo,inspection in adoptions.items():
        if inspection.get('schema')!='wellman.adoption-inspection/v1' or inspection.get('grants_authority') is not False or inspection.get('repository_id')!=repo or inspection.get('adoption_digest')!=payload_digest({k:v for k,v in inspection.items() if k!='adoption_digest'}):
            raise ContractError('ADOPTION_INSPECTION_INVALID')
    def timestamp(value):
        try:return datetime.fromisoformat(value.replace('Z','+00:00'))
        except ValueError as error:raise ContractError('INVALID_OBSERVATION_TIME') from error
    start,end=timestamp(observation['started_at']),timestamp(observation['finished_at'])
    if start>end:raise ContractError('INVALID_OBSERVATION_INTERVAL')
    evidence_index=ObservationEvidence(observation)
    def inspection_bound(inspection):
        if inspection is None:return False
        digest=payload_digest(inspection)
        return any(a['producer']=='wellman.adoption-inspection' and a['sha256']==digest
                   and evidence_index.bound(a['id'], repository_id=inspection['repository_id'])
                   for a in artifacts.values())
    bound_inspections={repo:inspection_bound(inspection) for repo,inspection in adoptions.items()}
    facts=defaultdict(list)
    for f in observation['features']:facts[(f['component_id'],f['id'])].append(f)
    def fact(cid, name, complete=False):
        values=facts.get((cid,name),[]);states=set();refs=set()
        for f in values:
            if complete and f['coverage']!='complete':continue
            evidence=f['evidence_refs']
            def bound(ref):
                negative=f['state']=='absent' or complete
                return evidence_index.bound(ref, component_id=cid, complete=negative)
            valid=evidence and all(bound(ref) for ref in evidence)
            if valid and f['state']!='unknown':states.add(f['state']);refs.update(evidence)
        return (next(iter(states)) if len(states)==1 else 'unknown',sorted(refs))
    def aggregate(cids, name, complete=False):
        parts=[fact(cid,name,complete) for cid in cids]
        state='present' if any(s=='present' for s,_ in parts) else 'absent' if parts and all(s=='absent' for s,_ in parts) else 'unknown'
        return state,sorted({r for s,refs in parts for r in refs if s==state})
    # Kahn ordering retains cycles as deferred diagnostics, never an install order.
    edges={i:[d['id'] for d in m['depends_on'] if d['id'] in metadata] for i,m in metadata.items()}
    remaining=set(edges);order=[]
    while remaining:
        ready=sorted(i for i in remaining if not (set(edges[i]) & remaining))
        if not ready:break
        order+=ready;remaining.difference_update(ready)
    cycles=remaining
    if cycles:diagnostics.append({'code':'DEPENDENCY_CYCLE','standards':sorted(cycles)})
    order+=sorted(cycles)
    candidates=sorted(STANDARDS_CATALOG);decisions=[];effective={}
    grouped=defaultdict(list)
    for c in sorted(components.values(),key=lambda c:c['id']):grouped[c['repository_id']].append(c)
    for repo,cset in sorted(grouped.items()):
        inspection=adoptions.get(repo)
        for identifier in candidates:
            m=metadata.get(identifier);scope=m['scope'] if m else RULES[identifier]['scope']
            groups=[cset] if scope in ('repository','workspace') else [[c] for c in cset]
            for group in groups:
                cids=[c['id'] for c in group];anchor=cids[0]
                current=current_adoption(inspection,identifier) if inspection else {'state':'unknown','revision':None,'manifest_digest':None,'lock_digest':None,'conformance':'unverified','evidence_refs':[],'exceptions':[]}
                adopted=bool(inspection and inspection['standards'].get(identifier,{}).get('adopted'))
                bound_adoption=bound_inspections.get(repo,False)
                if not bound_adoption:current.update(state='unknown',conformance='unverified')
                d={'repository_id':repo,'component_id':anchor,'standard_id':identifier,'scope':scope,
                   'applicability':'insufficient_data','action':'defer','current':current,
                   'target_revision':m['revision'] if m else None,'reasons':[], 'evidence_refs':[],
                   'depends_on':[dep['id'] for dep in m['depends_on']] if m else [],'conflicts':[],
                   'managed_files':sorted(set(m['managed_files'])) if m else [],'risk':'unknown',
                   'validators':sorted(set(m['validators'])) if m else [],'required_authorities':[],
                   'limitations':[]}
                effective[(repo,identifier,anchor)]=d;decisions.append(d)
                if not m:d['reasons']=['METADATA_MISSING'];continue
                references=[dep['id'] for dep in m['depends_on']]+m['conflicts_with']+m['supersedes']
                if any(ref not in STANDARDS_CATALOG for ref in references):
                    d['reasons']=['REFERENCED_STANDARD_UNKNOWN'];continue
                if repositories[repo]['identity']!='confirmed' or repositories[repo]['source_digest'] is None or scope=='workspace' or (scope in ('component','runtime') and group[0]['boundary']!='confirmed'):
                    d['reasons']=['SCOPE_UNCONFIRMED'];continue
                if any(q['code']=='SOURCE_CHANGED_DURING_SCAN' and (not q['affected_refs'] or set(q['affected_refs']) & {repo,*cids}) for q in observation['quality_issues']):
                    d['reasons']=['SOURCE_CHANGED_DURING_SCAN'];continue
                condition=m['applies_when'];all_values=[];any_values=[];refs=set()
                for operator,values in [('all',all_values),('any',any_values)]:
                    for predicate in condition[operator]:
                        state,evidence=aggregate(cids,predicate['feature']);refs.update(evidence)
                        values.append(None if state=='unknown' else state==predicate['is'])
                truth=_combine([_combine(all_values,'all'),_combine(any_values,'any') if any_values else True],'all')
                for requirement in m['requires_evidence']:
                    complete=requirement.startswith('complete:');name=requirement[len('complete:'):] if complete else requirement
                    state,evidence=aggregate(cids,name,complete);refs.update(evidence)
                    if truth is not False and state!='present':truth=None
                d['evidence_refs']=sorted(refs)
                d['applicability']='applicable' if truth is True else 'not_applicable' if truth is False else 'insufficient_data'
                if truth is None:d['reasons']=['EVIDENCE_INSUFFICIENT'];continue
                if truth is False:
                    d.update(action='keep',risk='low',reasons=['NOT_APPLICABLE_PRESERVE_ADOPTION' if adopted else 'NOT_APPLICABLE_NO_CHANGE']);continue
                if identifier in cycles:d['reasons']=['DEPENDENCY_CYCLE'];continue
                if current['state']=='unknown':d['reasons']=['ADOPTION_UNKNOWN' if bound_adoption else 'ADOPTION_OBSERVATION_UNBOUND'];continue
                if current['exceptions']:
                    d['reasons']=['EXCEPTION_REVIEW_REQUIRED'];continue
                if adopted and current['revision']==m['revision'] and current['state']!='drifted':
                    d.update(action='keep',risk='low',reasons=['TARGET_ALREADY_ADOPTED'])
                    if current['conformance']!='verified':d['limitations'].append('CONFORMANCE_UNVERIFIED')
                elif adopted and current['state']=='drifted':
                    if current['revision']!=m['revision'] and current['revision'] not in m['migration']['from_revisions']:
                        d['reasons']=['MIGRATION_UNAVAILABLE'];continue
                    d.update(action='repair',reasons=['LOCAL_DRIFT_REVIEW'],risk='high')
                    d['limitations'].append('LOCAL_CHANGES_MUST_BE_PRESERVED')
                elif adopted:
                    if current['revision'] not in m['migration']['from_revisions']:
                        d['reasons']=['MIGRATION_UNAVAILABLE'];continue
                    d.update(action='update',reasons=['DECLARED_MIGRATION'],risk='medium')
                elif inspection and inspection['coverage']=='complete':
                    d.update(action='add',reasons=['MATCHING_CAPABILITY_NO_ADOPTION'],risk='medium')
                else:d['reasons']=['ADOPTION_COVERAGE_UNKNOWN'];continue
                if d['action'] in ('add','update','repair'):
                    if not d['managed_files'] or not d['validators']:
                        d.update(action='defer',risk='unknown');d['reasons'].append('MANAGED_SCOPE_OR_VALIDATION_UNKNOWN')
                    if not m['effects']:
                        d.update(action='defer',risk='unknown');d['reasons'].append('EFFECTS_UNKNOWN')
                    undeclared = _managed_control_effects(d['managed_files']) - set(m['effects'])
                    if undeclared:
                        d.update(action='defer',risk='unknown')
                        d['reasons'].extend('MANAGED_EFFECT_UNDECLARED:' + effect for effect in sorted(undeclared))
                    if d['action'] != 'defer':
                        d['required_authorities']=['review-concrete-plan']
                        if set(m['effects']) & {'ci','hooks','permissions','deployment','removal'}:
                            d['risk']='high';d['required_authorities'].append('approve-declared-effects')
                        d['limitations'].append('PATCH_NOT_PREPARED')
                for old in m['supersedes']:
                    replaced=inspection and inspection['standards'].get(old,{}).get('adopted')
                    state,evidence=aggregate(cids,'replacement:'+old,True)
                    if replaced and state=='present' and d['action']=='add':
                        d.update(action='propose_replace',risk='high');d['reasons'].append('EXPLICIT_SUPERSEDES:'+old)
                        d['evidence_refs']=sorted(set(d['evidence_refs'])|set(evidence));d['required_authorities'].append('separate-removal-decision')
    # Dependencies/conflicts are interpreted in each component's effective scope.
    by_target=defaultdict(list)
    for d in decisions:by_target[(d['repository_id'],d['standard_id'])].append(d)
    def targets(d,identifier):
        # Repository decisions use one component as a display anchor. Their
        # relationships still cover every component in that repository.
        return [x for x in by_target.get((d['repository_id'],identifier),[]) if d['scope'] in ('repository','workspace') or x['scope'] in ('repository','workspace') or x['component_id']==d['component_id']]
    for d in decisions:
        m=metadata.get(d['standard_id'])
        inspection=adoptions.get(d['repository_id'])
        adopted=inspection and inspection['standards'].get(d['standard_id'],{}).get('adopted')
        if not m or (d['applicability']!='applicable' and not adopted):continue
        for dep in m['depends_on'] if d['applicability']=='applicable' else []:
            available=targets(d,dep['id'])
            if dep['id'] not in STANDARDS_CATALOG or not available or any(x['target_revision'] not in dep['revisions'] for x in available):
                d['action']='defer';d['reasons'].append('DEPENDENCY_REVISION_UNKNOWN:'+dep['id'])
        for conflict in m['conflicts_with']:
            available=targets(d,conflict)
            inspection=adoptions.get(d['repository_id'])
            active=inspection and inspection['standards'].get(conflict,{}).get('adopted')
            if active or any(x['applicability']=='applicable' for x in available):
                d['action']='defer';d['conflicts'].append(conflict);d['reasons'].append('STANDARD_CONFLICT:'+conflict)
                for other in available:
                    if other['applicability']=='applicable' or active:
                        other['action']='defer';other['conflicts'].append(d['standard_id']);other['reasons'].append('STANDARD_CONFLICT:'+d['standard_id'])
    # Re-evaluate until deferred dependencies have propagated through the DAG.
    for _ in range(len(metadata)+1):
        changed=False
        for d in decisions:
            if d['action'] in ('defer','keep'):continue
            for dep in d['depends_on']:
                required=targets(d,dep)
                if any(x['action']=='defer' or x['applicability']!='applicable' for x in required):
                    d['action']='defer';d['reasons'].append('DEPENDENCY_DEFERRED:'+dep);changed=True;break
        if not changed:break
    for d in decisions:
        d['reasons']=sorted(set(d['reasons']));d['conflicts']=sorted(set(d['conflicts']))
        d['depends_on']=sorted(set(d['depends_on']),key=lambda i:(order.index(i) if i in order else len(order),i))
        if d['action']=='defer':d['required_authorities']=[]
    if advisory is not None:
        if not isinstance(advisory,list):diagnostics.append({'code':'ADVISORY_UNAVAILABLE'})
        else:
            for suggestion in advisory:
                if not isinstance(suggestion,dict) or not isinstance(suggestion.get('standard_id'),str) or suggestion['standard_id'] not in STANDARDS_CATALOG:
                    diagnostics.append({'code':'ADVISORY_UNKNOWN_STANDARD'})
                elif not isinstance(suggestion.get('evidence_refs'),list) or not suggestion['evidence_refs'] or any(not isinstance(ref,str) or ref not in artifacts for ref in suggestion['evidence_refs']):
                    diagnostics.append({'code':'ADVISORY_EVIDENCE_INVALID'})
    positions={identifier:index for index,identifier in enumerate(order)}
    decisions.sort(key=lambda d:(d['repository_id'],d['component_id'],positions.get(d['standard_id'],len(order)),d['standard_id']))
    return {'mode':'recommendation','grants_authority':False,'executable':False,'decisions':decisions,
            'dependency_order':order,'diagnostics':diagnostics,'rule_digest':payload_digest({'version':RULE_VERSION,'candidate_rules':RULES,'effective_metadata':metadata})}
