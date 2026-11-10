"""Tests for Wellmanifest standards registry."""

from wellman.registry import (
    CONFORMANCE_LEVELS,
    PROFILES_CATALOG,
    STANDARDS_CATALOG,
    get_profile,
    get_standard,
    list_profiles,
    list_standards,
)


def test_standards_catalog_not_empty():
    standards = list_standards()
    assert len(standards) >= 20
    assert "wellmanifest/new-project" in STANDARDS_CATALOG
    assert "wellmanifest/git-lifecycle" in STANDARDS_CATALOG
    assert "wellmanifest/worktrees" in STANDARDS_CATALOG
    assert "wellmanifest/ticket-lifecycle" in STANDARDS_CATALOG
    assert "wellmanifest/merge" in STANDARDS_CATALOG
    assert "wellmanifest/agent" in STANDARDS_CATALOG
    assert "wellmanifest/nl-dsl-llm" in STANDARDS_CATALOG
    assert "wellmanifest/nl-api-llm" in STANDARDS_CATALOG
    assert "wellmanifest/python" in STANDARDS_CATALOG


def test_python_standard():
    py = get_standard("wellmanifest/python")
    assert py is not None
    assert py.id == "wellmanifest/python"
    assert py.minimum_level == "S1"
    assert py.execution_model == "local-conformance"
    assert "execution authority" in py.excludes
    assert "verified runtime conformance" in py.excludes
    assert "wellmanifest/semver" in py.requires
    assert "PYTHON-DIST-001" in py.description
    assert [k for k, v in STANDARDS_CATALOG.items() if v.minimum_level == "S0"] == []

    standards = list_standards()
    assert len(standards) >= 20
    assert "wellmanifest/new-project" in STANDARDS_CATALOG
    assert "wellmanifest/git-lifecycle" in STANDARDS_CATALOG
    assert "wellmanifest/worktrees" in STANDARDS_CATALOG
    assert "wellmanifest/ticket-lifecycle" in STANDARDS_CATALOG
    assert "wellmanifest/merge" in STANDARDS_CATALOG
    assert "wellmanifest/agent" in STANDARDS_CATALOG
    assert "wellmanifest/nl-dsl-llm" in STANDARDS_CATALOG
    assert "wellmanifest/nl-api-llm" in STANDARDS_CATALOG


def test_conformance_levels():
    for level in ("S0", "S1", "S2", "S3", "S4", "S5"):
        assert level in CONFORMANCE_LEVELS


def test_get_standard_alias_resolution():
    s1 = get_standard("wellmanifest/git-lifecycle")
    assert s1 is not None
    assert s1.id == "wellmanifest/git-lifecycle"

    # Alias
    s2 = get_standard("git")
    assert s2 is not None
    assert s2.id == "wellmanifest/git-lifecycle"

    s3 = get_standard("worktrees")
    assert s3 is not None
    assert s3.id == "wellmanifest/worktrees"

    s4 = get_standard("nl-api-llm")
    assert s4 is not None
    assert s4.id == "wellmanifest/nl-api-llm"

    s5 = get_standard("nl-api")
    assert s5 is not None
    assert s5.id == "wellmanifest/nl-api-llm"

    s6 = get_standard("wellmanifest/reuse")
    assert s6 is not None
    assert s6.id == "wellmanifest/reuse"
    assert s6.name == "Code Reuse & Deduplication Standard"

    s7 = get_standard("reuse")
    assert s7 is not None
    assert s7.id == "wellmanifest/reuse"


def test_profiles_catalog():
    profiles = list_profiles()
    assert len(profiles) >= 5
    baseline = get_profile("baseline")
    assert baseline is not None
    req_ids = [r["id"] for r in baseline.requirements]
    assert "wellmanifest/new-project" in req_ids
    assert "wellmanifest/git-lifecycle" in req_ids
    assert "wellmanifest/worktrees" in req_ids
    assert "wellmanifest/docs" in req_ids


def test_uri_and_configuration_standards_are_local_conformance_candidates():
    for name in ('nohardcode', 'taskand', 'uriprocess', 'nl-uri-dsl-llm'):
        standard = get_standard(name)
        assert standard.id == 'wellmanifest/' + name
        assert standard.minimum_level == 'S1'
        assert standard.execution_model == 'local-conformance'
        assert standard.schemas
        assert 'execution authority' in standard.excludes
        assert 'verified runtime conformance' in standard.excludes
    # They are component-specific candidates, not mandatory baseline adoption.
    baseline = {item['id'] for item in get_profile('baseline').requirements}
    assert not baseline.intersection({'wellmanifest/nohardcode', 'wellmanifest/taskand',
                                     'wellmanifest/uriprocess', 'wellmanifest/nl-uri-dsl-llm'})


def test_ssot_and_semver_are_local_conformance_standards():
    from wellman.registry import get_standard

    for alias in ("ssot", "semver"):
        pack = get_standard(alias)
        assert pack is not None and pack.id == f"wellmanifest/{alias}"
        assert pack.execution_model == "local-conformance"
        assert pack.minimum_level == "S1"
        assert "execution authority" in pack.excludes
        assert "verified runtime conformance" in pack.excludes


def test_conformance_pack_standards_registered_as_local_conformance(tmp_path, capsys):
    import json
    from wellman.cli import main

    expected = {
        "nolimits": (["wellmanifest/hostguard"], "GOV-NOLIMITS-MISSING"),
        "auth-lifecycle": (["wellmanifest/lifecycle"], "GOV-AUTH-LIFECYCLE-MISSING"),
        "secrets": (["wellmanifest/auth-lifecycle"], "GOV-SECRETS-MISSING"),
        "clonerd": ([], "GOV-CLONERD-MISSING"),
        "llm-account-tool": (["wellmanifest/account-runtime"], "GOV-LLM-ACCOUNT-MISSING"),
    }
    baseline = {item["id"] for item in get_profile("baseline").requirements}
    for alias, (requires, missing_code) in expected.items():
        canonical = f"wellmanifest/{alias}"
        pack = get_standard(alias)
        assert pack is not None and get_standard(canonical) is pack
        assert pack.id == canonical
        assert pack.minimum_level == "S1"
        assert pack.execution_model == "local-conformance"
        assert pack.requires == requires
        assert pack.schemas
        assert "execution authority" in pack.excludes
        assert "verified runtime conformance" in pack.excludes
        assert canonical not in baseline

        assert main(["info", canonical]) == 0
        capsys.readouterr()

        assert main(["check", "--standard", canonical, "--root", str(tmp_path), "--json"]) == 1
        report = json.loads(capsys.readouterr().out)
        assert all(f["code"] != "GOV-STANDARD-NOT-IMPLEMENTED" for f in report["findings"])
        assert any(f["code"] == missing_code for f in report["findings"])
