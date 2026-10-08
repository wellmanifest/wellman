import subprocess
import sys
from pathlib import Path

import pytest

from wellman.components import inventory_repository
from wellman.selection_contracts import ContractError

requires_toml = pytest.mark.skipif(sys.version_info < (3,11), reason='Positive TOML fixtures need stdlib tomllib; older runtimes report unsupported evidence')


def git(root,*args):
    return subprocess.run(['git','-C',str(root),*args],capture_output=True,text=True,check=True).stdout


def write(root,path,text):
    target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)


@pytest.fixture
def repo(tmp_path):
    root=tmp_path/'repo';root.mkdir()
    git(root,'init','-b','main')
    git(root,'config','user.name','Test')
    git(root,'config','user.email','test@example.invalid')
    git(root,'remote','add','origin','https://github.com/example/components.git')
    write(root,'package.json','{"name":"lib","source":"src/lib/main.py"}')
    write(root,'src/lib/main.py','value = 1\n')
    git(root,'add','.');git(root,'commit','-qm','Initial fixture')
    return root


def file(report,path):
    return next(f for f in report['files'] if f['path']==path)


@requires_toml
def test_component_boundaries_use_manifests_and_git(repo):
    write(repo,'Cargo.toml','[workspace]\nmembers=["crates/*"]\n')
    write(repo,'crates/worker/Cargo.toml','[package]\nname="worker"\nversion="0.1.0"\n')
    write(repo,'crates/worker/src/lib.rs','pub fn run() {}\n')
    write(repo,'desktop/package.json','{"name":"desktop","source":"src/main.ts"}')
    write(repo,'desktop/src/main.ts','export const x=1;')
    # Same-directory root manifests conflict explicitly instead of creating two products.
    report=inventory_repository(repo)
    components={c['path']:c for c in report['components']}
    assert components['.']['boundary']=='unknown'
    assert components['crates/worker']['name']=='worker'
    assert components['desktop']['name']=='desktop'
    assert len(components)==3
    assert file(report,'crates/worker/src/lib.rs')['component_id']==components['crates/worker']['id']
    assert file(report,'desktop/src/main.ts')['class']=='first_party'


@requires_toml
def test_rust_workspace_is_container_with_distinct_packages(repo):
    (repo/'package.json').unlink()
    write(repo,'Cargo.toml','[workspace]\nmembers=["crates/a","crates/b"]\n')
    for name in ('a','b'):
        write(repo,f'crates/{name}/Cargo.toml',f'[package]\nname="{name}"\nversion="0.1.0"\n')
    report=inventory_repository(repo)
    assert [(c['path'],c['kind']) for c in report['components']]==[('.','workspace'),('crates/a','package'),('crates/b','package')]
    assert all(c['boundary']=='confirmed' for c in report['components'])


def test_historical_and_generated_names_are_only_hints(repo):
    write(repo,'work/copy/pyproject.toml','[project]\nname="copy"\n')
    write(repo,'src/gen/schemas/schema.py','pass\n')
    report=inventory_repository(repo)
    assert len(report['components'])==1
    assert file(report,'work/copy/pyproject.toml')['class']=='unknown'
    assert file(report,'work/copy/pyproject.toml')['classification_hint']=='historical_copy'
    assert file(report,'src/gen/schemas/schema.py')['class']=='unknown'
    assert file(report,'src/gen/schemas/schema.py')['classification_hint']=='generated'


@pytest.mark.parametrize('kind',['generated','vendored','runtime_artifact','historical_copy'])
def test_explicit_nonproduct_scope_does_not_create_a_component(repo,kind):
    write(repo,'copy/pyproject.toml','[project]\nname="copy"\n')
    report=inventory_repository(repo,classification={kind:['copy/**']})
    assert len(report['components'])==1
    assert file(report,'copy/pyproject.toml')['class']==kind


@requires_toml
def test_explicit_first_party_policy_can_confirm_a_directory_named_work(repo):
    write(repo,'work/pyproject.toml','[project]\nname="worker"\n')
    report=inventory_repository(repo,classification={'first_party':['work/**','package.json']})
    assert {c['name'] for c in report['components']}=={'lib','worker'}


def test_classification_conflict_is_unknown(repo):
    report=inventory_repository(repo,classification={'first_party':['src/**'],'generated':['src/**']})
    assert file(report,'src/lib/main.py')['class']=='unknown'
    assert any(i['code']=='CLASSIFICATION_CONFLICT' for i in report['quality_issues'])
    assert not report['complete']


def test_source_inventory_binds_untracked_manifests_and_deletions(repo):
    initial=inventory_repository(repo)
    write(repo,'plugin/package.json','{"name":"plugin"}')
    changed=inventory_repository(repo)
    assert len(changed['components'])==2
    assert changed['source_digest']!=initial['source_digest']
    (repo/'src/lib/main.py').unlink()
    deleted=inventory_repository(repo)
    assert file(deleted,'src/lib/main.py')['kind']=='deleted'
    assert changed['source_digest']!=deleted['source_digest']


def test_local_digest_binds_staged_state_even_if_worktree_restored(repo):
    initial=inventory_repository(repo)
    write(repo,'src/lib/main.py','value = 2\n')
    git(repo,'add','src/lib/main.py')
    write(repo,'src/lib/main.py','value = 1\n')
    changed=inventory_repository(repo)
    assert initial['source_digest']==changed['source_digest']
    assert initial['local_changes_digest']!=changed['local_changes_digest']


def test_inventory_is_deterministic_and_does_not_import_code(repo,tmp_path):
    write(repo,'src/lib/poison.py','raise RuntimeError("must not import")\n')
    before=git(repo,'status','--porcelain')
    first=inventory_repository(repo);second=inventory_repository(repo)
    assert first==second
    assert git(repo,'status','--porcelain')==before


def test_symlink_escape_is_not_read(repo,tmp_path,monkeypatch):
    outside=tmp_path/'outside.py';outside.write_text('private sentinel')
    (repo/'src/lib/link.py').symlink_to(outside)
    original=Path.open
    def guarded(path,*args,**kwargs):
        assert path!=outside and path.name!='link.py'
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',guarded)
    report=inventory_repository(repo)
    assert not report['complete']
    assert any(i['path']=='src/lib/link.py' for i in report['quality_issues'])


def test_symlinked_repository_root_is_rejected(repo,tmp_path):
    link=tmp_path/'alias';link.symlink_to(repo,target_is_directory=True)
    with pytest.raises(ContractError,match='symlinks'):inventory_repository(link)


def test_missing_git_identity_remains_unconfirmed(tmp_path):
    write(tmp_path,'pyproject.toml','[project]\nname="library"\n')
    report=inventory_repository(tmp_path)
    assert report['identity']=='unconfirmed'
    assert report['components'][0]['boundary']=='unknown'
    assert not report['complete']


@pytest.mark.parametrize('manifest,contents',[
    ('Cargo.toml','[workspace]\nmembers=["../outside"]\n'),
    ('package.json','{"name":"pkg","workspaces":["../outside"]}'),
    ('pyproject.toml','[project]\nname="pkg"\n[tool.setuptools.package-dir]\n""="../outside"'),
])
def test_manifest_cannot_expand_scope_outside_repo(repo,manifest,contents):
    write(repo,manifest,contents)
    report=inventory_repository(repo)
    assert any(i['code']=='MANIFEST_UNREADABLE' for i in report['quality_issues'])


def test_invalid_and_oversized_manifests_have_coverage_gaps(repo):
    write(repo,'broken/package.json','not json')
    report=inventory_repository(repo)
    assert not report['complete']
    report=inventory_repository(repo,max_file_bytes=1)
    assert report['quality_issues'] and not report['complete']


def test_inventory_bounds_are_explicit(repo):
    with pytest.raises(ContractError,match='limit'):inventory_repository(repo,max_files=1)


def test_environment_secrets_are_excluded_without_reading(repo,monkeypatch):
    write(repo,'.env','private sentinel')
    original=Path.open
    def guarded(path,*args,**kwargs):
        assert path.name!='.env'
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',guarded)
    report=inventory_repository(repo)
    assert all(f['path']!='.env' for f in report['files'])
    assert any(i['code']=='SENSITIVE_FILE_EXCLUDED' for i in report['quality_issues'])


def test_unconfirmed_remote_does_not_expand_git_scope(repo):
    write(repo,'.gitignore','ignored/**\n')
    write(repo,'ignored/package.json','{"name":"private ignored copy"}')
    git(repo,'remote','remove','origin')
    report=inventory_repository(repo)
    assert report['identity']=='unconfirmed' and report['head'] is not None
    assert all(not f['path'].startswith('ignored/') for f in report['files'])


@pytest.mark.parametrize('arguments',[{'max_file_bytes':True},{'exclusions':'src/**'},{'classification':{'invented':['src/**']}}])
def test_invalid_scope_options_fail_closed(repo,arguments):
    with pytest.raises(ContractError):inventory_repository(repo,**arguments)


@requires_toml
def test_python_manifest_can_declare_additional_source_roots(repo):
    write(repo,'pyproject.toml','[project]\nname="lib"\n[tool.setuptools.packages.find]\nwhere=["src"]\n')
    report=inventory_repository(repo)
    assert report['components'][0]['boundary']=='confirmed'
    assert report['components'][0]['source_roots']==['src','src/lib']
