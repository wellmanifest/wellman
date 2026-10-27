"""Registered standard requirements must be visibly satisfied (ticket-062).

``wellman adopt`` writes ``.governance/standard-requirements.json``; ``wellman check``
has to enforce it instead of deciding docs adoption from ``manifest.json`` alone.
"""

import json
import subprocess

import pytest

from wellman.docs_adoption import expected_adoption
from wellman.validator import StandardsValidator


@pytest.fixture
def repository(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/acme/example.git"],
        cwd=tmp_path, check=True,
    )
    (tmp_path / ".governance").mkdir()
    (tmp_path / ".governance" / "manifest.json").write_text(
        json.dumps({"schema": "wellmanifest.manifest/v1",
                    "standard": {"id": "wellmanifest/new-project", "version": "0.20.92"}}),
        encoding="utf-8",
    )
    return tmp_path


def require(root, *ids):
    (root / ".governance" / "standard-requirements.json").write_text(json.dumps({
        "schema": "wellman.standard-requirements/v1",
        "profiles": ["baseline"],
        "requirements": [{"id": i, "minimumLevel": "S3"} for i in ids],
    }), encoding="utf-8")


def adopt_docs(root, index=True):
    (root / ".governance" / "docs.json").write_text(json.dumps(expected_adoption(root)), encoding="utf-8")
    if index:
        (root / "docs").mkdir(exist_ok=True)
        (root / "docs" / "README.md").write_text("# Docs\n", encoding="utf-8")


def codes(root):
    return {f.code: f for f in StandardsValidator(root).run_all_validations()}


def test_registered_docs_requirement_is_enforced_without_manifest_profile(repository):
    require(repository, "wellmanifest/docs")
    found = codes(repository)
    assert "GOV-DOCS-MISSING" in found
    assert found["GOV-DOCS-MISSING"].severity == "ERROR"


def test_docs_requirement_needs_the_docs_index(repository):
    require(repository, "wellmanifest/docs")
    adopt_docs(repository, index=False)
    found = codes(repository)
    assert "GOV-DOCS-INDEX-MISSING" in found
    assert found["GOV-DOCS-INDEX-MISSING"].path == "docs/README.md"
    assert found["GOV-DOCS-INDEX-MISSING"].severity == "ERROR"


def test_satisfied_docs_requirement_passes(repository):
    require(repository, "wellmanifest/docs")
    adopt_docs(repository)
    found = codes(repository)
    assert not {"GOV-DOCS-MISSING", "GOV-DOCS-INDEX-MISSING"} & set(found)


def test_logs_requirement_needs_an_error_catalog(repository):
    require(repository, "wellmanifest/logs")
    found = codes(repository)
    assert found["GOV-LOGS-MISSING"].severity == "ERROR"
    assert found["GOV-LOGS-MISSING"].path == "errors/README.md"
    (repository / "errors").mkdir()
    (repository / "errors" / "README.md").write_text("# Errors\n", encoding="utf-8")
    assert "GOV-LOGS-MISSING" not in codes(repository)


def test_requirements_without_a_local_check_are_listed_as_unverified(repository):
    require(repository, "wellmanifest/merge", "wellmanifest/poa")
    found = codes(repository)
    unverified = found["GOV-REQUIREMENT-UNVERIFIED"]
    assert unverified.severity == "WARNING"
    assert "wellmanifest/merge" in unverified.message and "wellmanifest/poa" in unverified.message


def test_no_requirements_file_keeps_previous_behaviour(repository):
    found = codes(repository)
    assert not {"GOV-DOCS-MISSING", "GOV-LOGS-MISSING", "GOV-REQUIREMENT-UNVERIFIED"} & set(found)


def test_malformed_requirements_file_is_reported(repository):
    (repository / ".governance" / "standard-requirements.json").write_text("{", encoding="utf-8")
    assert codes(repository)["GOV-REQUIREMENTS-JSON"].severity == "ERROR"


def test_implemented_runner_standards_are_not_flagged_unverified(repository):
    from wellman.runner import ConformanceRunner
    require(
        repository,
        "wellmanifest/git-lifecycle",
        "wellmanifest/agent",
        "wellmanifest/session-recovery",
        "wellmanifest/reuse",
    )
    found = codes(repository)
    assert "GOV-REQUIREMENT-UNVERIFIED" not in found
    runner_codes = {f.code: f for f in ConformanceRunner(repository).run_all()}
    assert "GOV-REUSE-NO-RECEIPT" in runner_codes


def test_local_ci_adopted_deployment_and_poa_are_not_flagged_unverified(repository):
    from wellman.runner import ConformanceRunner
    (repository / ".governance" / "local-ci-publication.json").write_text(
        json.dumps({"schema": "new-project.local-ci-publication/v1", "scope": {"mode": "all"}}),
        encoding="utf-8",
    )
    require(
        repository,
        "wellmanifest/deployment",
        "wellmanifest/poa",
        "wellmanifest/authority-lifecycle",
        "wellmanifest/semver",
    )
    found = codes(repository)
    assert "GOV-REQUIREMENT-UNVERIFIED" not in found
    runner_codes = {f.code: f for f in ConformanceRunner(repository).run_all()}
    assert "GOV-SEMVER-MISSING" in runner_codes
