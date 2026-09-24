import json

import pytest

from wellman.local_ci import (DEFAULT_POLICY, POLICY_PATH, applies_to, ensure_default_policy,
                              read_policy, validate_policy)
from wellman.runner import ConformanceRunner


def restricted(*repositories):
    return {"schema": "new-project.local-ci-publication/v1",
            "scope": {"mode": "restricted", "repositories": list(repositories)}}


def test_absent_policy_means_every_repository(tmp_path):
    policy, problem = read_policy(tmp_path)
    assert problem is None and policy == DEFAULT_POLICY
    assert applies_to(policy, "maskservice/c2004") and applies_to(policy, "anyone/anything")


def test_restriction_only_narrows_the_default():
    policy = restricted("maskservice/*", "subactor/onedev-agent")
    assert validate_policy(policy) == []
    assert applies_to(policy, "maskservice/c2004")
    assert applies_to(policy, "subactor/onedev-agent")
    assert not applies_to(policy, "subactor/validator-agent")
    assert not applies_to(policy, "semcod/koru")


@pytest.mark.parametrize("document", [
    [],
    {"schema": "other/v1", "scope": {"mode": "all"}},
    {"schema": "new-project.local-ci-publication/v1", "scope": {"mode": "restricted"}},
    restricted(),
    restricted("*"),
    restricted("a/b", "a/b"),
    {"schema": "new-project.local-ci-publication/v1", "scope": {"mode": "all", "repositories": ["a/b"]}},
    {"schema": "new-project.local-ci-publication/v1", "scope": {"mode": "all"}, "grants": ["merge"]},
])
def test_invalid_policies_are_rejected(document):
    assert validate_policy(document)


def test_malformed_policy_keeps_unrestricted_default_and_warns(tmp_path):
    (tmp_path / ".governance").mkdir()
    (tmp_path / POLICY_PATH).write_text(json.dumps(restricted()), encoding="utf-8")
    policy, problem = read_policy(tmp_path)
    assert policy == DEFAULT_POLICY and problem
    findings = ConformanceRunner(tmp_path).check_local_ci_publication()
    assert [f.code for f in findings] == ["GOV-LOCAL-CI-001"]
    assert findings[0].severity == "WARNING"


def test_valid_or_absent_policy_has_no_finding(tmp_path):
    assert ConformanceRunner(tmp_path).check_local_ci_publication() == []
    (tmp_path / ".governance").mkdir()
    (tmp_path / POLICY_PATH).write_text(json.dumps(restricted("maskservice/*")), encoding="utf-8")
    assert ConformanceRunner(tmp_path).check_local_ci_publication() == []


def test_ensure_writes_default_once_and_never_replaces_a_restriction(tmp_path):
    preview = ensure_default_policy(tmp_path, dry_run=True)
    assert preview["changed"] and not (tmp_path / POLICY_PATH).exists()
    created = ensure_default_policy(tmp_path)
    assert created["changed"]
    assert json.loads((tmp_path / POLICY_PATH).read_text()) == DEFAULT_POLICY
    assert not ensure_default_policy(tmp_path)["changed"]

    (tmp_path / POLICY_PATH).write_text(json.dumps(restricted("maskservice/*")), encoding="utf-8")
    kept = ensure_default_policy(tmp_path)
    assert not kept["changed"] and kept["policy"]["scope"]["mode"] == "restricted"
    assert json.loads((tmp_path / POLICY_PATH).read_text())["scope"]["mode"] == "restricted"
    assert not list((tmp_path / ".governance").glob(".local-ci-*"))


def test_ensure_refuses_symlinked_policy(tmp_path):
    (tmp_path / ".governance").mkdir()
    target = tmp_path / "elsewhere.json"
    target.write_text("{}")
    (tmp_path / POLICY_PATH).symlink_to(target)
    with pytest.raises(ValueError):
        ensure_default_policy(tmp_path)
