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
