"""Wellmanifest Schemas and Standards Validation Engine.

Provides deterministic validation for:
- JSON/YAML schema conformance
- Standard pack routing and profile composition
- Adoption manifests and lock files
- Standard level conformance (S0 to S5)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from wellman.registry import (
    CONFORMANCE_LEVELS,
    EXECUTION_MODELS,
    PROFILES_CATALOG,
    STANDARDS_CATALOG,
    get_profile,
    get_standard,
)
from wellman.docs_adoption import validate_adoption as validate_docs_adoption


@dataclass
class Finding:
    """A standard compliance or validation finding."""

    code: str
    message: str
    severity: str = "ERROR"  # ERROR, WARNING, INFO
    path: str = ""
    remediation: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "path": self.path,
            "remediation": self.remediation,
        }

    def __str__(self) -> str:
        loc = f" [{self.path}]" if self.path else ""
        return f"{self.code} {self.severity}: {self.message}{loc}"


def calculate_sha256(path: Path) -> str:
    """Compute sha256 hash of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def get_schemas_dir() -> Path:
    """Return path to the bundled schemas directory."""
    return Path(__file__).parent / "schemas"


def load_bundled_schema(schema_name: str) -> Optional[Dict[str, Any]]:
    """Load a JSON schema from the bundled directory."""
    if not schema_name.endswith(".json"):
        schema_name += ".schema.json"
    p = get_schemas_dir() / schema_name
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def validate_json_structure(data: Any, schema: Dict[str, Any], path_prefix: str = "") -> List[Finding]:
    """Lightweight pure-python schema validator (checks required fields, types, enum)."""
    findings: List[Finding] = []

    if not isinstance(schema, dict):
        return findings

    expected_type = schema.get("type")
    if expected_type == "object" and not isinstance(data, dict):
        findings.append(Finding(
            code="SCHEMA-TYPE-001",
            message=f"Expected object, got {type(data).__name__}",
            path=path_prefix,
        ))
        return findings
    elif expected_type == "array" and not isinstance(data, list):
        findings.append(Finding(
            code="SCHEMA-TYPE-001",
            message=f"Expected array, got {type(data).__name__}",
            path=path_prefix,
        ))
        return findings
    elif expected_type == "string" and not isinstance(data, str):
        findings.append(Finding(
            code="SCHEMA-TYPE-001",
            message=f"Expected string, got {type(data).__name__}",
            path=path_prefix,
        ))
        return findings

    # Check required fields for objects
    if isinstance(data, dict):
        required = schema.get("required", [])
        for field_name in required:
            if field_name not in data:
                findings.append(Finding(
                    code="SCHEMA-REQUIRED-001",
                    message=f"Missing required field: '{field_name}'",
                    path=f"{path_prefix}.{field_name}" if path_prefix else field_name,
                    remediation=f"Add field '{field_name}' as required by schema.",
                ))

        # Check property constraints
        properties = schema.get("properties", {})
        for prop, prop_schema in properties.items():
            if prop in data and isinstance(prop_schema, dict):
                findings.extend(validate_json_structure(
                    data[prop], prop_schema, f"{path_prefix}.{prop}" if path_prefix else prop
                ))

    return findings


class StandardsValidator:
    """Validator for repository governance files against Wellmanifest standards."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.gov_dir = self.root / ".governance"

    def validate_standard_packs(self) -> List[Finding]:
        """Validate standard-packs.json routing rules."""
        findings: List[Finding] = []
        catalog_path = self.gov_dir / "standard-packs.json"
        if not catalog_path.is_file():
            # Check bundled catalog
            catalog_path = get_schemas_dir() / "standard-packs.json"

        if not catalog_path.is_file():
            return [Finding("STD-PACK-MISSING", "standard-packs.json catalog file not found", severity="WARNING")]

        try:
            data = json.loads(catalog_path.read_text(encoding="utf-8"))
        except Exception as e:
            return [Finding("STD-PACK-JSON", f"Invalid standard-packs.json: {e}")]

        packs = data.get("packs", [])
        pack_ids: Set[str] = set()
        concerns: Set[str] = set()

        for pack in packs:
            if not isinstance(pack, dict):
                findings.append(Finding("STD-PACK-FORMAT", "Each pack must be an object"))
                continue
            pack_id = pack.get("id")
            if not pack_id:
                findings.append(Finding("STD-PACK-NO-ID", "Pack is missing 'id'"))
                continue
            if pack_id in pack_ids:
                findings.append(Finding("STD-PACK-DUPLICATE-ID", f"Duplicate standard pack id: {pack_id}"))
            pack_ids.add(pack_id)

            owns = pack.get("owns", [])
            for concern in owns:
                if concern in concerns:
                    findings.append(Finding(
                        "STD-PACK-DUPLICATE-OWNER",
                        f"Duplicate normative concern owner '{concern}' in pack {pack_id}",
                    ))
                concerns.add(concern)

        # Validate profiles
        profiles = data.get("profiles", {})
        for name, profile in profiles.items():
            if not isinstance(profile, dict):
                continue
            for parent in profile.get("extends", []):
                if parent not in profiles and parent not in PROFILES_CATALOG:
                    findings.append(Finding(
                        "STD-PACK-INVALID-PROFILE",
                        f"Profile '{name}' extends unknown parent profile '{parent}'",
                    ))
            for req in profile.get("requirements", []):
                req_id = req.get("id")
                if req_id and req_id not in pack_ids and req_id not in STANDARDS_CATALOG:
                    findings.append(Finding(
                        "STD-PACK-UNKNOWN-REQ",
                        f"Profile '{name}' requires unregistered pack '{req_id}'",
                    ))

        return findings

    def validate_adoption_manifest(self) -> List[Finding]:
        """Validate .governance/manifest.json and manifest.lock.json."""
        findings: List[Finding] = []
        manifest_path = self.gov_dir / "manifest.json"
        lock_path = self.gov_dir / "manifest.lock.json"

        if not manifest_path.is_file():
            findings.append(Finding(
                "GOV-MANIFEST-MISSING",
                "Missing .governance/manifest.json",
                severity="ERROR",
                remediation="Run `wellman adopt wellmanifest/new-project` to bootstrap governance.",
            ))
            return findings

        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            return [Finding("GOV-MANIFEST-JSON", f"Malformed manifest.json: {e}")]

        standard_info = manifest_data.get("standard", {})
        standard_id = standard_info.get("id")
        standard_version = standard_info.get("version")

        if not standard_id:
            findings.append(Finding("GOV-MANIFEST-NO-STANDARD", "manifest.json missing 'standard.id'"))
        elif not self._is_registered_adoption_target(standard_id):
            findings.append(Finding(
                "GOV-MANIFEST-UNKNOWN-STANDARD",
                f"manifest.json names unknown standard or profile '{standard_id}'",
                remediation="Use a registered standard ID or profile name from `wellman standards` or `wellman profiles`.",
            ))
        if not standard_version:
            findings.append(Finding("GOV-MANIFEST-NO-VERSION", "manifest.json missing 'standard.version'"))

        # Check lockfile
        if lock_path.is_file():
            try:
                lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
                managed_files = lock_data.get("managedFiles", {})
                for rel_path, expected_hash in managed_files.items():
                    target = self.root / rel_path
                    if not target.is_file():
                        findings.append(Finding(
                            "GOV-SYNC-001",
                            f"Managed file is missing: {rel_path}",
                            path=rel_path,
                            remediation="Run `wellman adopt --upgrade` to restore managed standard files.",
                        ))
                    else:
                        actual_hash = calculate_sha256(target)
                        if actual_hash != expected_hash:
                            findings.append(Finding(
                                "GOV-SYNC-001",
                                f"Managed file digest differs: {rel_path} (expected={expected_hash[:8]}..., actual={actual_hash[:8]}...)",
                                path=rel_path,
                                remediation="Restore file or update lock via `wellman adopt --upgrade`.",
                            ))
            except Exception as e:
                findings.append(Finding("GOV-LOCK-JSON", f"Malformed manifest.lock.json: {e}"))
        else:
            findings.append(Finding(
                "GOV-LOCK-MISSING",
                "Missing .governance/manifest.lock.json",
                severity="WARNING",
                remediation="Use the managed wellmanifest/new-project adoption flow to generate a lockfile.",
            ))

        return findings

    @staticmethod
    def _is_registered_adoption_target(standard_id: Any) -> bool:
        if not isinstance(standard_id, str):
            return False
        if get_standard(standard_id) is not None:
            return True
        prefix = "profile:"
        return standard_id.startswith(prefix) and get_profile(standard_id[len(prefix):]) is not None

    def validate_standard_adoption(self) -> List[Finding]:
        """Validate .governance/standard-adoption.json."""
        findings: List[Finding] = []
        p = self.gov_dir / "standard-adoption.json"
        if not p.is_file():
            return findings  # Optional file

        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            adoptions = data.get("adoptions", [])
            for item in adoptions:
                item_id = item.get("id")
                level = item.get("level", "S0")
                if level not in CONFORMANCE_LEVELS:
                    findings.append(Finding(
                        "STD-LEVEL-INVALID",
                        f"Standard {item_id} has invalid conformance level: {level}",
                        path="standard-adoption.json",
                    ))
        except Exception as e:
            findings.append(Finding("STD-ADOPT-JSON", f"Malformed standard-adoption.json: {e}"))

        return findings

    def validate_docs(self, required: bool = False) -> List[Finding]:
        """Validate repository-bound ``wellmanifest/docs`` adoption metadata."""

        return [
            Finding(
                code=item["code"],
                message=item["message"],
                path=".governance/docs.json",
                remediation=item.get("remediation", ""),
            )
            for item in validate_docs_adoption(self.root, required=required)
        ]

    def docs_adoption_required(self) -> bool:
        """Return whether the selected manifest/profile requires docs adoption."""

        manifest_path = self.gov_dir / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False

        selected = []
        standard = manifest.get("standard", {})
        if isinstance(standard, dict) and isinstance(standard.get("id"), str):
            selected.append(standard["id"])
        for item in manifest.get("standards", []):
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                selected.append(item["id"])

        def profile_includes(profile_name: str, target: str, seen: set) -> bool:
            if profile_name in seen:
                return False
            seen.add(profile_name)
            profile_name = profile_name.removeprefix("profile:")
            profile = get_profile(profile_name)
            if profile is None:
                return False
            if any(item.get("id") == target for item in profile.requirements):
                return True
            return any(profile_includes(parent, target, seen) for parent in profile.extends)

        return any(
            item == "wellmanifest/docs"
            or (item.startswith("profile:") and profile_includes(item, "wellmanifest/docs", set()))
            for item in selected
        )

    def run_all_validations(self) -> List[Finding]:
        """Execute complete suite of standards validations."""
        all_findings: List[Finding] = []
        all_findings.extend(self.validate_adoption_manifest())
        all_findings.extend(self.validate_standard_packs())
        all_findings.extend(self.validate_standard_adoption())
        all_findings.extend(self.validate_docs(required=self.docs_adoption_required()))
        return all_findings
