"""Tests for StandardsValidator and schema verification."""

import json
from pathlib import Path
import pytest
from wellman.validator import (
    StandardsValidator,
    calculate_sha256,
    get_schemas_dir,
    load_bundled_schema,
    validate_json_structure,
)


@pytest.fixture
def docs_repository(tmp_path):
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/acme/example.git"],
        cwd=tmp_path, check=True,
    )
    (tmp_path / ".governance").mkdir()
    return tmp_path


@pytest.mark.parametrize("revision,digest", [
    ("aa92136b4e94f48355c39fb206286aba024c6aa4",
     "af5fde2d52e1c292e569cd47a4068f0e42181a8f8fb9fc21737a569bee9a206f"),
    ("19efafbeb18923cfd51cc69bd519330488500137",
     "fac05e720ec49370ba393e817a4a03b895d7ed33828e09b3420f9fcfb09264b0"),
])
def test_published_docs_adoption_is_preserved(docs_repository, revision, digest):
    path = docs_repository / ".governance/docs.json"
    original = json.dumps({
        "schema": "wellmanifest.docs/adoption/v1", "repository": "acme/example",
        "standard": "wellmanifest/docs", "source_revision": revision,
        "policy_sha256": digest,
    })
    path.write_text(original)

    assert StandardsValidator(docs_repository).validate_docs(required=True) == []
    assert path.read_text() == original


@pytest.mark.parametrize("overrides", [
    {"source_revision": "0" * 40},
    {"policy_sha256": "0" * 64},
    {"source_revision": "19efafbeb18923cfd51cc69bd519330488500137"},
    {"repository": "acme/other"},
    {"standard": "wellmanifest/other"},
    {"schema": "wellmanifest.docs/adoption/v999"},
    {"extra": "unreviewed"},
    {"source_revision": []},
])
def test_docs_compatibility_rejects_unbound_records(docs_repository, overrides):
    from wellman.docs_adoption import expected_adoption

    record = expected_adoption(docs_repository)
    record.update(overrides)
    (docs_repository / ".governance/docs.json").write_text(json.dumps(record))

    findings = StandardsValidator(docs_repository).validate_docs(required=True)

    assert [item.code for item in findings] == ["GOV-DOCS-DRIFT"]


def test_new_docs_adoption_uses_published_050(docs_repository):
    from wellman.docs_adoption import render_adoption

    record = json.loads(render_adoption(docs_repository))

    assert record["source_revision"] == "aa92136b4e94f48355c39fb206286aba024c6aa4"
    assert record["policy_sha256"] == "af5fde2d52e1c292e569cd47a4068f0e42181a8f8fb9fc21737a569bee9a206f"


def test_bundled_schemas_directory():
    d = get_schemas_dir()
    assert d.is_dir()
    manifest_schema = load_bundled_schema("manifest")
    assert manifest_schema is not None
    assert manifest_schema.get("type") == "object"


def test_validate_json_structure():
    schema = {
        "type": "object",
        "required": ["name", "version"],
        "properties": {
            "name": {"type": "string"},
            "version": {"type": "string"},
        },
    }
    # Valid data
    valid_data = {"name": "test", "version": "1.0.0"}
    findings = validate_json_structure(valid_data, schema)
    assert len(findings) == 0

    # Invalid data - missing required field
    invalid_data = {"name": "test"}
    findings = validate_json_structure(invalid_data, schema)
    assert len(findings) == 1
    assert findings[0].code == "SCHEMA-REQUIRED-001"


def test_validator_on_empty_dir(tmp_path):
    validator = StandardsValidator(tmp_path)
    findings = validator.run_all_validations()
    # Missing manifest.json should produce an ERROR finding
    error_codes = [f.code for f in findings if f.severity == "ERROR"]
    assert "GOV-MANIFEST-MISSING" in error_codes


def test_validator_rejects_unknown_adoption_target(tmp_path):
    gov_dir = tmp_path / ".governance"
    gov_dir.mkdir()
    (gov_dir / "manifest.json").write_text(
        json.dumps({"standard": {"id": "wellmanifest/nope", "version": "0.20.35"}}),
        encoding="utf-8",
    )

    findings = StandardsValidator(tmp_path).validate_adoption_manifest()

    assert "GOV-MANIFEST-UNKNOWN-STANDARD" in [finding.code for finding in findings]


def test_validator_rejects_docs_adoption_bound_to_another_repository(tmp_path):
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/acme/example.git"],
        cwd=tmp_path,
        check=True,
    )
    gov_dir = tmp_path / ".governance"
    gov_dir.mkdir()
    (gov_dir / "docs.json").write_text(
        json.dumps({
            "schema": "wellmanifest.docs/adoption/v1",
            "repository": "acme/other",
            "standard": "wellmanifest/docs",
            "source_revision": "19efafbeb18923cfd51cc69bd519330488500137",
            "policy_sha256": "fac05e720ec49370ba393e817a4a03b895d7ed33828e09b3420f9fcfb09264b0",
        }),
        encoding="utf-8",
    )

    findings = StandardsValidator(tmp_path).validate_docs(required=True)

    assert [finding.code for finding in findings] == ["GOV-DOCS-DRIFT"]


def test_validator_requires_docs_for_baseline_profile(tmp_path):
    gov_dir = tmp_path / ".governance"
    gov_dir.mkdir()
    (gov_dir / "manifest.json").write_text(
        json.dumps({
            "schema": "wellmanifest.manifest/v1",
            "standard": {"id": "profile:baseline", "version": "0.20.36"},
        }),
        encoding="utf-8",
    )

    findings = StandardsValidator(tmp_path).run_all_validations()

    assert "GOV-DOCS-MISSING" in [finding.code for finding in findings]
