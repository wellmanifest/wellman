"""Tests for Wellman CLI commands."""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from wellman import __version__
from wellman.cli import main
from wellman.cli import _worktree_admission


def test_cli_version(capsys):
    ret = main(["--version"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "wellman" in captured.out


def test_cli_standards(capsys):
    ret = main(["standards"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "wellmanifest/git-lifecycle" in captured.out
    assert "wellmanifest/worktrees" in captured.out


def test_cli_standards_json(capsys):
    ret = main(["standards", "--json"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert isinstance(data, list)
    assert any(s["id"] == "wellmanifest/git-lifecycle" for s in data)


def test_cli_info(capsys):
    ret = main(["info", "wellmanifest/new-project"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "New Project" in captured.out
    assert "Owned Concerns:" in captured.out


def test_cli_info_unknown(capsys):
    ret = main(["info", "nonexistent/standard"])
    assert ret == 1
    captured = capsys.readouterr()
    assert "Unknown standard" in captured.err


def test_cli_profiles(capsys):
    ret = main(["profiles"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Profile: baseline" in captured.out


def test_cli_profiles_json(capsys):
    ret = main(["profiles", "--json"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert isinstance(data, list)
    assert any(p["name"] == "baseline" for p in data)


def test_cli_check_rejects_unknown_standard(capsys, tmp_path):
    ret = main(["check", "--root", str(tmp_path), "--standard", "wellmanifest/nope", "--json"])

    assert ret == 1
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] is False
    assert result["findings"][0]["code"] == "GOV-STANDARD-UNKNOWN"


def test_cli_check_fails_closed_for_unimplemented_standard(capsys, tmp_path):
    ret = main(["check", "--root", str(tmp_path), "--standard", "wellmanifest/docs", "--json"])

    assert ret == 1
    result = json.loads(capsys.readouterr().out)
    assert result["findings"][0]["code"] == "GOV-DOCS-MISSING"


def test_cli_check_rejects_git_checkout_below_system_tmp(capsys, tmp_path):
    git(tmp_path, "init", "-q")

    ret = main([
        "check", "--root", str(tmp_path),
        "--standard", "wellmanifest/worktrees", "--json",
    ])

    assert ret == 1
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] is False
    assert result["findings"][0]["code"] == "GOV-WORKTREE-ADMISSION-001"


def test_cli_adopt_rejects_unknown_target_without_writing(capsys, tmp_path):
    ret = main(["adopt", "wellmanifest/nope", "--root", str(tmp_path), "--bootstrap"])

    assert ret == 1
    assert not (tmp_path / ".governance").exists()
    assert "Unknown standard or profile" in capsys.readouterr().err


def test_cli_adopt_does_not_overwrite_manifest_without_force(capsys, tmp_path):
    manifest = tmp_path / ".governance" / "manifest.json"
    manifest.parent.mkdir()
    manifest.write_text('{"preserve": true}\n', encoding="utf-8")

    ret = main(["adopt", "baseline", "--root", str(tmp_path), "--bootstrap"])

    assert ret == 1
    assert manifest.read_text(encoding="utf-8") == '{"preserve": true}\n'
    assert "without --force" in capsys.readouterr().err

    ret = main([
        "adopt", "baseline", "--root", str(tmp_path), "--force", "--bootstrap",
        "--repository", "acme/example",
    ])

    assert ret == 0
    adopted = json.loads(manifest.read_text(encoding="utf-8"))
    assert adopted["standard"]["id"] == "profile:baseline"


def test_cli_adopt_uses_running_package_version(capsys, tmp_path):
    ret = main([
        "adopt", "baseline", "--root", str(tmp_path), "--bootstrap",
        "--repository", "acme/example",
    ])

    assert ret == 0
    manifest = json.loads((tmp_path / ".governance" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["standard"] == {"id": "profile:baseline", "version": __version__}
    assert "Adoption scaffolded" in capsys.readouterr().out


@pytest.mark.parametrize('target', ['baseline', 'wellmanifest/new-project', 'wellmanifest/worktrees'])
@pytest.mark.parametrize('schema', ['new-project.governance/v2', 'new-project.governance/v3'])
def test_explicit_adoption_cannot_replace_native_governance(tmp_path, capsys, target, schema):
    gov = tmp_path / '.governance'
    gov.mkdir()
    manifest = gov / 'manifest.json'
    original = json.dumps({'schema': schema, 'approvalEvidence': {'requiredBindings': ['headSha']}}).encode()
    manifest.write_bytes(original)

    assert main(['adopt', target, '--root', str(tmp_path), '--bootstrap',
                 '--force', '--repository', 'acme/example']) == 1
    assert {p.name: p.read_bytes() for p in gov.iterdir()} == {'manifest.json': original}
    assert 'pinned new-project adoption' in capsys.readouterr().err


@pytest.mark.parametrize('target', ['baseline', 'wellmanifest/new-project', 'wellmanifest/worktrees'])
@pytest.mark.parametrize('manifest_present', [False, True])
def test_explicit_adoption_preserves_locked_and_partial_adoption(tmp_path, capsys, target, manifest_present):
    gov = tmp_path / '.governance'
    gov.mkdir()
    (gov / 'manifest.lock.json').write_text('{"schema":"new-project.lock/v1"}\n')
    if manifest_present:
        (gov / 'manifest.json').write_text('{"schema":"wellmanifest.manifest/v1"}\n')
    original = {p.name: p.read_bytes() for p in gov.iterdir()}

    assert main(['adopt', target, '--root', str(tmp_path), '--bootstrap',
                 '--force', '--repository', 'acme/example']) == 1
    assert {p.name: p.read_bytes() for p in gov.iterdir()} == original
    assert 'pinned new-project adoption' in capsys.readouterr().err


def test_explicit_adoption_preserves_unreadable_manifest(tmp_path, capsys):
    gov = tmp_path / '.governance'
    gov.mkdir()
    (gov / 'manifest.json').write_bytes(b'{"schema":')
    assert main(['adopt', 'baseline', '--root', str(tmp_path), '--bootstrap',
                 '--force', '--repository', 'acme/example']) == 1
    assert {p.name: p.read_bytes() for p in gov.iterdir()} == {'manifest.json': b'{"schema":'}
    assert 'cannot inspect existing adoption' in capsys.readouterr().err


def test_auto_registration_preserves_native_governance_and_lock(tmp_path, capsys):
    gov = tmp_path / '.governance'
    gov.mkdir()
    (gov / 'manifest.json').write_text('{"schema":"new-project.governance/v2"}\n')
    (gov / 'manifest.lock.json').write_text('{"schema":"new-project.lock/v1"}\n')
    original = {p.name: p.read_bytes() for p in gov.iterdir()}
    assert main(['adopt', 'auto', '--root', str(tmp_path), '--bootstrap', '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['conformance'] == 'unverified'
    assert all((gov / name).read_bytes() == content for name, content in original.items())
    assert (gov / 'standard-requirements.json').is_file()


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.mark.parametrize(
    "directory,branch,expected_code",
    [
        (".worktrees/ticket-021--admission", "ticket/021-admission", None),
        (".worktrees/ticket-1000--admission", "ticket/1000-admission", None),
        (".worktrees/ticket-021--admission", "ticket/022-admission", "GOV-WORKTREE-ADMISSION-004"),
        (".worktrees/ticket-021--admission", "ticket/021-other", "GOV-WORKTREE-ADMISSION-004"),
        (".worktrees/ticket-021--admission", "ticket-021-admission", "GOV-WORKTREE-ADMISSION-004"),
        (".worktrees/ticket-021--admission", None, "GOV-WORKTREE-ADMISSION-004"),
        (".worktrees/nested/ticket-021--admission", "ticket/021-admission", "GOV-WORKTREE-ADMISSION-003"),
        ("legacy/ticket-021--admission", "ticket/021-admission", "GOV-WORKTREE-ADMISSION-003"),
    ],
)
def test_registered_worktree_admission_uses_canonical_v5_identity(directory, branch, expected_code):
    # Admission deliberately rejects /tmp. Keep actual Git fixtures in ignored
    # repository-local storage, then remove their entire temporary registration.
    cache = Path.cwd() / ".subactor" / "cache" / "admission-tests"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as temporary:
        primary = Path(temporary) / "primary"
        primary.mkdir()
        git(primary, "init", "-q")
        git(primary, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "--allow-empty", "-qm", "fixture")
        linked = primary / directory
        linked.parent.mkdir(parents=True, exist_ok=True)
        args = ["worktree", "add"]
        args += ["-b", branch] if branch else ["--detach"]
        git(primary, *args, str(linked), "HEAD")
        assert _worktree_admission(primary) is None
        finding = _worktree_admission(linked)
        assert (finding.code if finding else None) == expected_code


@pytest.mark.parametrize('target', ['auto', 'baseline'])
def test_adopt_requires_explicit_non_git_bootstrap(tmp_path, capsys, target):
    assert main(['adopt', target, '--root', str(tmp_path)]) == 1
    assert '--bootstrap' in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []
    assert main([
        'adopt', target, '--root', str(tmp_path), '--bootstrap',
        '--repository', 'acme/example',
    ]) == 0
    assert (tmp_path / '.governance' / 'standard-requirements.json').is_file()


@pytest.mark.parametrize('explicit_root', [True, False])
@pytest.mark.parametrize('bootstrap', [True, False])
def test_adopt_from_nested_directory_uses_git_root(tmp_path, monkeypatch, capsys, explicit_root, bootstrap):
    git(tmp_path, 'init', '-q')
    nested = tmp_path / 'src' / 'deep'
    nested.mkdir(parents=True)
    argv = ['adopt', '--json']
    if bootstrap:
        argv.append('--bootstrap')
    if explicit_root:
        argv += ['--root', str(nested)]
    else:
        monkeypatch.chdir(nested)
    argv += ['--repository', 'acme/example']
    assert main(argv) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['path'] == str(tmp_path / '.governance' / 'standard-requirements.json')
    assert not (nested / '.governance').exists()


def test_adopt_linked_worktree_does_not_write_primary(tmp_path, capsys):
    primary, linked = tmp_path / 'primary', tmp_path / 'linked'
    primary.mkdir()
    git(primary, 'init', '-q')
    git(primary, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
        'commit', '--allow-empty', '-qm', 'fixture')
    git(primary, 'worktree', 'add', '--detach', str(linked), 'HEAD')
    nested = linked / 'nested'
    nested.mkdir()
    assert main(['adopt', '--root', str(nested), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['path'].startswith(str(linked) + '/')
    assert not (primary / '.governance').exists()
    assert not (nested / '.governance').exists()


@pytest.mark.parametrize('target', ['auto', 'baseline'])
@pytest.mark.parametrize('link_name', ['.governance', '.governance/manifest.json', '.governance/manifest.lock.json',
                                     '.governance/standard-packs.json',
                                     '.governance/standard-requirements.json'])
def test_adopt_rejects_symlink_targets_before_any_write(tmp_path, capsys, target, link_name):
    repository = tmp_path / 'repository'
    repository.mkdir()
    outside = tmp_path / 'outside'
    link = repository / link_name
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside, target_is_directory=link_name == '.governance')
    assert main(['adopt', target, '--root', str(repository), '--bootstrap', '--force']) == 1
    assert 'symlink' in capsys.readouterr().err
    assert link.is_symlink()
    assert not outside.exists()
    assert not (repository / '.governance' / 'standard-requirements.json').is_file()


def test_adopt_rejects_symlink_ancestor_and_symlink_dotdot(tmp_path, capsys):
    real = tmp_path / 'real'
    real.mkdir()
    (real / 'nested').mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(real, target_is_directory=True)
    for target in (alias / 'nested', alias / '..' / 'real'):
        assert main(['adopt', '--root', str(target), '--bootstrap']) == 1
        assert 'symlink' in capsys.readouterr().err
    assert not (real / '.governance').exists()


def test_adopt_ignores_inherited_git_location_overrides(tmp_path, monkeypatch):
    own, other = tmp_path / 'own', tmp_path / 'other'
    own.mkdir()
    other.mkdir()
    git(own, 'init', '-q')
    git(other, 'init', '-q')
    monkeypatch.setenv('GIT_DIR', str(other / '.git'))
    monkeypatch.setenv('GIT_WORK_TREE', str(other))
    assert main(['adopt', '--root', str(own), '--repository', 'acme/own']) == 0
    assert (own / '.governance' / 'standard-requirements.json').exists()
    assert not (other / '.governance').exists()


def test_bootstrap_does_not_hide_broken_or_bare_git_metadata(tmp_path):
    broken, bare = tmp_path / 'broken', tmp_path / 'bare'
    broken.mkdir()
    (broken / '.git').write_text('gitdir: missing\n')
    bare.mkdir()
    git(bare, 'init', '--bare', '-q')
    for root in (broken, bare):
        assert main(['adopt', '--root', str(root), '--bootstrap']) == 1
        assert not (root / '.governance').exists()


def test_cli_adopt_auto_with_repeatable_standard_flag(tmp_path, capsys):
    ret = main([
        'adopt', 'auto', '--root', str(tmp_path), '--bootstrap',
        '--standard', 'wellmanifest/nl-dsl-llm',
        '-s', 'wellmanifest/twin-lifecycle',
        '--json',
    ])
    assert ret == 0
    result = json.loads(capsys.readouterr().out)
    req_ids = {r['id'] for r in result['registration']['requirements']}
    assert 'wellmanifest/nl-dsl-llm' in req_ids
    assert 'wellmanifest/twin-lifecycle' in req_ids


def test_cli_adopt_auto_rejects_unknown_standard_flag(tmp_path, capsys):
    ret = main([
        'adopt', 'auto', '--root', str(tmp_path), '--bootstrap',
        '--standard', 'unknown/nonexistent-standard',
    ])
    assert ret == 1
    assert 'Unknown standard' in capsys.readouterr().err


def test_cli_adopt_explicit_rejects_standard_flag(tmp_path, capsys):
    ret = main([
        'adopt', 'baseline', '--root', str(tmp_path), '--bootstrap',
        '--standard', 'wellmanifest/nl-dsl-llm',
    ])
    assert ret == 1
    assert '--standard' in capsys.readouterr().err


def test_recommend_cli_register_is_explicit_additive_and_excludes_llm(tmp_path, capsys, monkeypatch):
    import sys
    from types import SimpleNamespace
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    graph = tmp_path / 'ast.json'
    graph.write_text(json.dumps({'project_path': str(tmp_path), 'modules': {
        'tool': {'file': 'cli.py', 'imports': ['click']}}}))
    def complete(*args, **kwargs):
        return SimpleNamespace(content='{"standards":[{"id":"wellmanifest/llm","reason":"planned"}]}', provider='test', model='fixture')
    monkeypatch.setitem(sys.modules, 'subllm', SimpleNamespace(complete=complete))
    args = ['recommend', '--root', str(tmp_path), '--ast', str(graph), '--json', '--llm']
    assert main(args) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview['advice']['status'] == 'advisory'
    assert not (tmp_path / '.governance').exists()
    assert main(args + ['--register']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['registration']['changed']
    requirements = tmp_path / '.governance' / 'standard-requirements.json'
    before = requirements.read_bytes()
    assert 'wellmanifest/llm' not in [item['id'] for item in json.loads(before)['requirements']]
    assert main(args + ['--register']) == 0
    result = json.loads(capsys.readouterr().out)
    assert not result['registration']['changed'] and requirements.read_bytes() == before


def test_recommend_cli_bad_evidence_fails_before_writes(tmp_path, capsys):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    assert main(['recommend', '--root', str(tmp_path), '--evidence', 'bad', '--register']) == 1
    assert 'TOOL=JSON_PATH' in capsys.readouterr().err
    assert not (tmp_path / '.governance').exists()


def test_recommend_fleet_is_bounded_read_only_and_builds_existing_plans(tmp_path, capsys):
    for name in ['library', 'service']:
        project = tmp_path / name
        project.mkdir()
        subprocess.run(['git', 'init', '-q', str(project)], check=True)
    assert main(['recommend', '--root', str(tmp_path), '--fleet', '--plan', '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result['reports']) == 2 and not result['applied'] and not result['grantsAuthority']
    assert all(report['adoptionPlans'] for report in result['reports'])
    assert all(not (tmp_path / name / '.governance').exists() for name in ['library', 'service'])
    assert main(['recommend', '--root', str(tmp_path), '--fleet', '--max-projects', '1']) == 1
    assert 'exceeds max-projects' in capsys.readouterr().err
    assert main(['recommend', '--root', str(tmp_path), '--fleet', '--register']) == 1
    assert 'read-only' in capsys.readouterr().err
@pytest.fixture
def evidence_cli(tmp_path):
    from wellman.applicability import build_catalog

    root = tmp_path / "source"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "remote",
            "add",
            "origin",
            "https://github.com/acme/library.git",
        ],
        check=True,
    )
    (root / "package.json").write_text('{"name":"library","source":"src/main.js"}')
    (root / "src").mkdir()
    (root / "src/main.js").write_text("export const value=1;\n")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "Fixture",
        ],
        check=True,
    )
    cat = build_catalog(
        {"wellmanifest/new-project": "a" * 40},
        revision="b" * 40,
        trusted_source="explicit fixture",
        metadata={
            "wellmanifest/new-project": {
                "managed_files": ["AGENTS.md"],
                "validators": ["review contract"],
                "effects": ["files"],
            }
        },
    )
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(cat))
    return (
        root,
        catalog,
        [
            "recommend",
            "--root",
            str(root),
            "--selection-plan",
            "--catalog",
            str(catalog),
            "--json",
        ],
    )


def test_selection_plan_cli_schema_reasons_and_no_implicit_effects(
    evidence_cli, capsys, monkeypatch
):
    import wellman.adoption as adoption
    import wellman.cli as cli
    from wellman.selection_contracts import validate_document

    root, _, args = evidence_cli
    before = {
        p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }

    def forbidden(*args, **kwargs):
        raise AssertionError("Unrequested effect")

    monkeypatch.setattr(adoption, "recommend", forbidden)
    monkeypatch.setattr(adoption, "register", forbidden)
    monkeypatch.setattr(cli, "feed_to_planfile", forbidden)
    assert main(args) == 0
    plan = json.loads(capsys.readouterr().out)
    validate_document(plan)
    assert not plan["executable"] and not plan["grants_authority"]
    d = next(
        d for d in plan["decisions"] if d["standard_id"] == "wellmanifest/new-project"
    )
    assert (
        d["action"] == "add" and d["evidence_refs"] and d["target_revision"] == "a" * 40
    )
    assert {
        p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()
    } == before


@pytest.mark.parametrize(
    "flags",
    [
        ["--register"],
        ["--analyze"],
        ["--fleet"],
        ["--plan"],
        ["--llm"],
        ["--ast", "missing.json"],
        ["--evidence", "code2llm=missing.json"],
        ["--hint", "agent"],
    ],
)
def test_selection_cli_rejects_legacy_effect_or_advisory_flags_before_execution(
    evidence_cli, capsys, flags
):
    root, _, args = evidence_cli
    assert main(args + flags) == 1
    assert "cannot combine" in capsys.readouterr().err
    assert not (root / ".governance").exists()


def test_selection_cli_requires_explicit_pins_and_opt_in(evidence_cli, capsys):
    root, catalog, _ = evidence_cli
    assert main(["recommend", "--root", str(root), "--selection-plan"]) == 1
    assert "requires --catalog" in capsys.readouterr().err
    assert (
        main(
            ["recommend", "--root", str(root), "--catalog", str(catalog), "--register"]
        )
        == 1
    )
    assert "require --selection-plan" in capsys.readouterr().err
    assert not (root / ".governance").exists()


def _save_selection_observation(root, destination, **options):
    from wellman.selection_contracts import canonical_bytes
    from wellman.selection_plan import capture_repository

    b = capture_repository(root, **options)
    destination.mkdir()
    for name, data in [
        ("observation", b["observation"]),
        ("inventory", b["inventory"]),
        ("adoption", b["adoptions"]["acme/library"]),
    ]:
        (destination / (name + ".json")).write_bytes(canonical_bytes(data))
    return destination / "observation.json"


def test_selection_cli_replays_same_saved_observation_deterministically(
    evidence_cli, tmp_path, capsys
):
    root, _, args = evidence_cli
    observation = _save_selection_observation(root, tmp_path / "snapshot")
    assert main(args + ["--observation", str(observation)]) == 0
    first = json.loads(capsys.readouterr().out)
    assert main(args + ["--observation", str(observation)]) == 0
    assert json.loads(capsys.readouterr().out) == first


def test_selection_cli_recovers_digest_bound_exclusions_from_saved_snapshot(evidence_cli,tmp_path,capsys):
    root,_,args=evidence_cli
    observation=_save_selection_observation(root,tmp_path/'snapshot',exclusions=['bench/**','**/src/gen/schemas/**'])
    assert main(args+['--observation',str(observation)])==0
    assert json.loads(capsys.readouterr().out)['schema']=='wellman.selection-plan/v1'


def test_selection_cli_requires_explicit_nondefault_classification_policy(evidence_cli,tmp_path,capsys):
    root,_,args=evidence_cli
    classification={'generated':['never/**']}
    observation=_save_selection_observation(root,tmp_path/'snapshot',classification=classification)
    assert main(args+['--observation',str(observation)])==1
    assert '--scope-policy' in capsys.readouterr().err
    policy=tmp_path/'policy.json';policy.write_text(json.dumps({'classification':classification}))
    assert main(args+['--observation',str(observation),'--scope-policy',str(policy)])==0
    assert json.loads(capsys.readouterr().out)['schema']=='wellman.selection-plan/v1'


@pytest.mark.parametrize("changed", ["source", "evidence", "missing"])
def test_selection_cli_rejects_stale_snapshot_before_export(
    evidence_cli, tmp_path, capsys, changed
):
    root, _, args = evidence_cli
    obs = _save_selection_observation(root, tmp_path / "snapshot")
    if changed == "source":
        (root / "src/main.js").write_text("export const value=2;\n")
    elif changed == "evidence":
        (obs.parent / "inventory.json").write_text("{}")
    else:
        (obs.parent / "adoption.json").unlink()
    target = tmp_path / "backlog"
    assert (
        main(args + ["--observation", str(obs), "--export-planfile", str(target)]) == 1
    )
    assert "PLAN_STALE" in capsys.readouterr().err
    assert not target.exists()


@pytest.mark.parametrize(
    "invalid", ["duplicate", "symlink", "wrong-schema", "scope-policy"]
)
def test_selection_cli_bounded_data_inputs_fail_closed(
    evidence_cli, tmp_path, capsys, invalid
):
    _, catalog, args = evidence_cli
    if invalid == "duplicate":
        catalog.write_text('{"schema":"x","schema":"y"}')
    elif invalid == "symlink":
        outside = tmp_path / "outside.json"
        outside.write_bytes(catalog.read_bytes())
        catalog.unlink()
        catalog.symlink_to(outside)
    elif invalid == "wrong-schema":
        catalog.write_text('{"schema":"wellman.standard-selection/v1"}')
    else:
        policy = tmp_path / "policy.json"
        policy.write_text('{"exclusions":"everything"}')
        args += ["--scope-policy", str(policy)]
    assert main(args) == 1
    assert capsys.readouterr().err


def test_selection_cli_explicit_export_returns_separate_receipt(
    evidence_cli, tmp_path, capsys
):
    pytest.importorskip("planfile.core.store")
    _, _, args = evidence_cli
    target = tmp_path / "backlog"
    target.mkdir()
    assert main(args + ["--export-planfile", str(target)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["schema"] == "wellman.selection-export/v1"
    assert (
        result["plan"]["schema"] == "wellman.selection-plan/v1"
        and result["export"]["ok"]
    )
    assert result["export"]["created"] > 0 and not result["export"]["remote_effects"]


def test_selection_cli_module_entrypoint_defines_bridge_before_main(evidence_cli):
    import os
    import sys

    _, _, args = evidence_cli
    environment = dict(
        os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src")
    )
    result = subprocess.run(
        [sys.executable, "-m", "wellman.cli", *args],
        capture_output=True,
        text=True,
        env=environment,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["schema"] == "wellman.selection-plan/v1"


@pytest.fixture
def ssot_cli(evidence_cli, tmp_path):
    from wellman.selection_contracts import payload_digest
    from wellman.selection_plan import capture_repository

    root, _, _ = evidence_cli
    observation = capture_repository(root)['observation']
    component = observation['components'][0]['id']
    observation['stages'] = [{
        'id': 'contracts-stage', 'tool': 'contracts', 'component_id': component,
        'started_at': observation['started_at'], 'finished_at': observation['finished_at'],
        'status': 'complete', 'exit_code': 0, 'truncated': False,
        'coverage': 'complete', 'errors': [], 'artifact_refs': ['contracts'],
    }]
    observation['artifacts'] = [{
        'id': 'contracts', 'path': 'contracts.json', 'media_type': 'application/json',
        'size_bytes': 3, 'sha256': '5' * 64, 'producer': 'contracts',
        'origin_observation_id': observation['observation_id'], 'freshness': 'verified',
    }]
    declaration = {
        'schema': 'wellman.ssot-declarations/v1',
        'observation_digest': payload_digest(observation),
        'records': [{
            'id': name, 'domain': 'billing', 'kind': 'rule', 'key': 'quota',
            'component_id': component, 'role': 'owner', 'content_digest': '6' * 64,
            'evidence_refs': ['contracts'], 'source_id': None, 'source_digest': None,
        } for name in ('owner', 'competitor')],
    }
    obs = tmp_path / 'observation.json'
    decl = tmp_path / 'declarations.json'
    obs.write_text(json.dumps(observation))
    decl.write_text(json.dumps(declaration))
    return root, obs, decl, ['ssot', '--observation', str(obs), '--declarations', str(decl)]


def test_ssot_cli_reports_review_proposals_without_execution(ssot_cli, capsys, monkeypatch):
    import wellman.cli as cli
    import wellman.adoption as adoption

    root, obs, decl, args = ssot_cli
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    inputs = (obs.read_bytes(), decl.read_bytes())

    def forbidden(*args, **kwargs):
        raise AssertionError('Unrequested effect')

    monkeypatch.setattr(adoption, 'register', forbidden)
    monkeypatch.setattr(cli, 'feed_to_planfile', forbidden)
    monkeypatch.setattr(cli.subprocess, 'run', forbidden)
    assert main(args + ['--json']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['schema'] == 'wellman.ssot-analysis/v1'
    assert report['findings'][0]['code'] == 'SSOT_MULTIPLE_OWNERS'
    assert not report['grants_authority'] and not report['applied']
    assert not report['refactoring_proposals'][0]['executable']
    assert (obs.read_bytes(), decl.read_bytes()) == inputs
    assert {p: p.read_bytes() for p in root.rglob('*') if p.is_file()} == before


def test_ssot_cli_partial_snapshot_defers_and_text_explains_limits(ssot_cli, capsys):
    from wellman.selection_contracts import payload_digest

    _, obs, decl, args = ssot_cli
    observation = json.loads(obs.read_text())
    observation['stages'][0]['status'] = 'partial'
    obs.write_text(json.dumps(observation))
    declarations = json.loads(decl.read_text())
    declarations['observation_digest'] = payload_digest(observation)
    decl.write_text(json.dumps(declarations))
    assert main(args) == 0
    text = capsys.readouterr().out
    assert 'defer: SSOT_EVIDENCE_INSUFFICIENT' in text
    assert '0 nonexecutable review proposals' in text
    assert 'Current repository freshness and undeclared contracts are not checked' in text


@pytest.mark.parametrize('case', ['stale', 'duplicate', 'symlink', 'missing', 'oversized', 'invalid'])
def test_ssot_cli_rejects_invalid_inputs_without_report(ssot_cli, capsys, case):
    from wellman.selection_contracts import MAX_DOCUMENT_BYTES

    _, obs, decl, args = ssot_cli
    if case == 'stale':
        d = json.loads(decl.read_text())
        d['observation_digest'] = '0' * 64
        decl.write_text(json.dumps(d))
    elif case == 'duplicate':
        decl.write_text('{"schema":"x","schema":"y"}')
    elif case == 'symlink':
        target = decl.with_suffix('.saved')
        decl.rename(target)
        decl.symlink_to(target)
    elif case == 'missing':
        decl.unlink()
    elif case == 'oversized':
        with decl.open('wb') as stream:
            stream.truncate(MAX_DOCUMENT_BYTES + 1)
    else:
        obs.write_text('[]')
    assert main(args + ['--json']) == 1
    output = capsys.readouterr()
    assert not output.out and 'SSOT analysis failed:' in output.err


def test_ssot_cli_module_entrypoint(ssot_cli):
    import os
    import sys

    _, _, _, args = ssot_cli
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).parents[1] / 'src'))
    result = subprocess.run([sys.executable, '-m', 'wellman.cli', *args, '--json'],
                            env=env, text=True, capture_output=True, check=True)
    assert json.loads(result.stdout)['coverage'] == 'declared-contracts-only'


def test_ssot_cli_rejects_symlinked_parent_directory(ssot_cli, tmp_path, capsys):
    _, obs, decl, _ = ssot_cli
    alias = tmp_path / 'aliased-inputs'
    alias.symlink_to(obs.parent, target_is_directory=True)
    assert main(['ssot', '--observation', str(alias / obs.name),
                 '--declarations', str(decl), '--json']) == 1
    output = capsys.readouterr()
    assert not output.out and 'must not traverse a symlink' in output.err


@pytest.fixture
def ssot_export_cli(ssot_cli, tmp_path):
    from wellman.selection_contracts import canonical_bytes, payload_digest
    from wellman.selection_plan import capture_repository

    root, obs, decl, args = ssot_cli
    bundle = capture_repository(root)
    observation = bundle['observation']
    obs.write_text(json.dumps(observation))
    declaration = json.loads(decl.read_text())
    declaration['observation_digest'] = payload_digest(observation)
    for row in declaration['records']:
        row['component_id'] = observation['components'][0]['id']
        row['evidence_refs'] = ['inventory']
    decl.write_text(json.dumps(declaration))
    artifacts = tmp_path / 'ssot-artifacts'
    artifacts.mkdir()
    (artifacts / 'inventory.json').write_bytes(canonical_bytes(bundle['inventory']))
    (artifacts / 'adoption.json').write_bytes(canonical_bytes(bundle['adoptions']['acme/library']))
    context = tmp_path / 'ssot-context.json'
    context.write_text(json.dumps({'repository_roots': {'acme/library': str(root)},
                                  'adoptions': bundle['adoptions'], 'artifact_root': str(artifacts)}))
    target = tmp_path / 'ssot-review'
    target.mkdir()
    return root, obs, decl, context, target, args


def test_ssot_cli_export_receipt_dedupes_and_preserves_terminal(ssot_export_cli, capsys):
    Store = pytest.importorskip('planfile.core.store').Store
    root, obs, decl, context, target, args = ssot_export_cli
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    inputs = [p.read_bytes() for p in (obs, decl, context)]
    command = args + ['--export-planfile', str(target), '--export-context', str(context), '--json']
    assert main(command) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt['schema'] == 'wellman.ssot-backlog-receipt/v1'
    assert receipt['count'] == receipt['created'] == 1
    assert not receipt['executable'] and not receipt['grants_authority'] and not receipt['remote_effects']
    assert main(command) == 0
    assert json.loads(capsys.readouterr().out)['tickets'][0]['state'] == 'reused'
    native = Store(target)
    task = native.get_ticket(receipt['tickets'][0]['id'])
    assert task.executor.kind == 'human' and task.execution.queue == 'wellman-ssot-review'
    completed = native.update_ticket(task.id, status='done', expected_updated_at=task.updated_at.isoformat())
    assert main(command) == 0
    assert json.loads(capsys.readouterr().out)['tickets'][0]['state'] == 'preserved_terminal'
    assert native.get_ticket(task.id).model_dump(mode='json') == completed.model_dump(mode='json')
    assert [p.read_bytes() for p in (obs, decl, context)] == inputs
    assert {p: p.read_bytes() for p in root.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('option', ['--export-planfile', '--export-context'])
def test_ssot_cli_export_requires_paired_explicit_options(ssot_cli, tmp_path, capsys, option):
    *_, args = ssot_cli
    assert main(args + [option, str(tmp_path / 'unused')]) == 1
    output = capsys.readouterr()
    assert not output.out and 'must be used together' in output.err
    assert not (tmp_path / 'unused').exists()


@pytest.mark.parametrize('change', ['source', 'artifact', 'source-target', 'artifact-target', 'empty-target'])
def test_ssot_cli_export_rejects_drift_and_unsafe_targets(ssot_export_cli, capsys, change):
    pytest.importorskip('planfile.core.store')
    root, _, _, context, target, args = ssot_export_cli
    data = json.loads(context.read_text())
    if change == 'source':
        (root / 'src/main.js').write_text('export const value=2;\n')
    elif change == 'artifact':
        (Path(data['artifact_root']) / 'inventory.json').write_text('{}')
    elif change == 'source-target':
        target = root / 'backlog'
    elif change == 'artifact-target':
        target = Path(data['artifact_root']) / 'backlog'
    else:
        target = ''
    assert main(args + ['--export-context', str(context), '--export-planfile', str(target), '--json']) == 1
    output = capsys.readouterr()
    assert not output.out and 'SSOT analysis failed:' in output.err
    assert not (root / '.planfile').exists()
    assert not (Path(data['artifact_root']) / '.planfile').exists()


@pytest.mark.parametrize('change', ['list', 'extra', 'roots', 'adoptions', 'artifact', 'options', 'missing', 'duplicate', 'symlink', 'oversized'])
def test_ssot_cli_export_context_fails_closed(ssot_export_cli, capsys, change):
    from wellman.selection_contracts import MAX_DOCUMENT_BYTES

    _, _, _, context, target, args = ssot_export_cli
    data = json.loads(context.read_text())
    if change == 'list':
        data = []
    elif change == 'extra':
        data['exec'] = 'unexpected'
    elif change == 'roots':
        data['repository_roots'] = []
    elif change == 'adoptions':
        data['adoptions'] = {}
    elif change == 'artifact':
        data['artifact_root'] = None
    elif change == 'options':
        data['inventory_options'] = []
    context.write_text(json.dumps(data))
    if change == 'missing':
        context.unlink()
    elif change == 'duplicate':
        context.write_text('{"repository_roots":{},"repository_roots":{}}')
    elif change == 'symlink':
        saved = context.with_suffix('.saved')
        context.rename(saved)
        context.symlink_to(saved)
    elif change == 'oversized':
        with context.open('wb') as stream:
            stream.truncate(MAX_DOCUMENT_BYTES + 1)
    assert main(args + ['--export-context', str(context), '--export-planfile', str(target), '--json']) == 1
    output = capsys.readouterr()
    assert not output.out and 'SSOT analysis failed:' in output.err
    assert not (target / '.planfile').exists()


def test_ssot_cli_export_relative_context_paths_bind_to_file_not_cwd(ssot_export_cli, capsys, monkeypatch, tmp_path):
    pytest.importorskip('planfile.core.store')
    root, _, _, context, target, args = ssot_export_cli
    data = json.loads(context.read_text())
    data['repository_roots']['acme/library'] = root.relative_to(context.parent).as_posix()
    data['artifact_root'] = Path(data['artifact_root']).relative_to(context.parent).as_posix()
    context.write_text(json.dumps(data))
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert main(args + ['--export-context', str(context), '--export-planfile', str(target)]) == 0
    text = capsys.readouterr().out
    assert 'current source and saved artifact hashes verified' in text
    assert '1 created' in text and 'No execution authority granted' in text
    assert not (elsewhere / '.planfile').exists()


def test_ssot_cli_snapshot_never_calls_export_adapter(ssot_cli, capsys, monkeypatch):
    import wellman.ssot_backlog as adapter
    def forbidden(*args, **kwargs):
        raise AssertionError('Unrequested export')
    monkeypatch.setattr(adapter, 'export_ssot_backlog', forbidden)
    assert main(ssot_cli[-1] + ['--json']) == 0
    assert json.loads(capsys.readouterr().out)['schema'] == 'wellman.ssot-analysis/v1'
