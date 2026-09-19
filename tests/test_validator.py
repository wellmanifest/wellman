"""Tests for StandardsValidator and schema verification."""

import json
from pathlib import Path
from wellman.validator import (
    StandardsValidator,
    calculate_sha256,
    get_schemas_dir,
    load_bundled_schema,
    validate_json_structure,
)


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
