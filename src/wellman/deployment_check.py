"""Inspect a WellManifest deployment descriptor and independently identified binding offline."""
from __future__ import annotations

import argparse
import hashlib
import json
from importlib import resources
from pathlib import Path
from typing import Optional

from .validator import Finding


def _unique_map(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate property")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("non-JSON constant")


def _inspect_descriptor(root: Path):
    try:
        with (root / "deployment.json").open("rb") as stream:
            raw = stream.read(1_048_577)
        if len(raw) > 1_048_576:
            raise ValueError("oversized descriptor")
        definition = json.loads(raw, object_pairs_hook=_unique_map, parse_constant=_invalid_constant)
    except FileNotFoundError:
        return None, [Finding("GOV-DEPLOYMENT-CONTRACT-MISSING", "Consumer deployment.json is missing.",
                              path="deployment.json", remediation="Declare the immutable source, target binding and verification in a wellmanifest.deployment/v1 descriptor.")]
    except (OSError, ValueError, RecursionError):
        return None, [Finding("GOV-DEPLOYMENT-CONTRACT-INVALID", "Cannot read an unambiguous deployment JSON object.",
                              path="deployment.json", remediation="Check readability, JSON syntax, duplicate keys and the 1 MiB limit.")]
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return None, [Finding("GOV-DEPLOYMENT-CHECKER-UNAVAILABLE", "Draft 2020-12 schema validation is unavailable.",
                              remediation="Install jsonschema 4.x in the environment running this inspection.")]
    # The upstream schema is part of this package. All its references are local.
    schema = json.loads(resources.files("wellman.schemas").joinpath("deployment.schema.json").read_bytes())
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    findings = []
    for error in validator.iter_errors(definition):
        location = ".".join(str(part) for part in error.absolute_path) or "root"
        if error.validator == "required" and isinstance(error.instance, dict):
            missing = sorted(set(error.validator_value) - error.instance.keys())
            location += "." + ",".join(missing)
        finding = Finding("GOV-DEPLOYMENT-CONTRACT-INVALID",
                          f"Deployment field {location} fails the {error.validator} constraint.",
                          path="deployment.json", remediation="Check the field against the canonical deployment v1 schema.")
        if finding not in findings:
            findings.append(finding)
        if len(findings) == 20:
            break
    if findings:
        return None, findings
    strategy = definition["strategy"]
    if strategy["type"] == "canary":
        stages = strategy["stages"]
        if stages[-1] != 100 or stages != sorted(stages):
            return None, [Finding("GOV-DEPLOYMENT-CANARY-STAGES", "Canary stages must increase and end at 100.",
                                  path="deployment.json", remediation="Order the percentages and finish the plan at 100 percent.")]
    return definition, []


def inspect_deployment(root: Path, binding_ref: Optional[str] = None, binding_file: Optional[Path] = None) -> dict:
    """The operator supplies the independently resolved logical name and exact bytes as a pair."""
    definition, findings = _inspect_descriptor(root)
    status = "unchecked"
    target = None
    if definition is not None:
        target = definition["target"]
        status = "declared"
        if binding_ref is not None or binding_file is not None:
            if binding_ref != target["bindingRef"] or binding_file is None:
                status = "reference_mismatch"
            else:
                digest = hashlib.sha256()
                try:
                    with binding_file.open("rb") as stream:
                        for block in iter(lambda: stream.read(65536), b""):
                            digest.update(block)
                    status = "digest_matches" if "sha256:" + digest.hexdigest() == target["bindingDigest"] else "digest_mismatch"
                except OSError:
                    status = "unreadable"
            if status != "digest_matches":
                findings.append(Finding("GOV-DEPLOYMENT-BINDING-UNVERIFIED", f"Trusted inventory comparison returned {status}.",
                                        remediation="Resolve the declared logical target through the owning executor and compare the exact versioned bytes."))
    return {"standard": "wellmanifest/deployment", "valid": not findings,
            "target": target, "binding_status": status, "runtime_enforcement": "not_checked",
            "deployment_authorized": False, "findings": [f.to_dict() for f in findings]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Directory containing deployment.json")
    parser.add_argument("--binding-ref", help="Logical name obtained from the trusted executor inventory")
    parser.add_argument("--binding-file", type=Path, help="Exact record bytes resolved by that inventory")
    args = parser.parse_args(argv)
    if (args.binding_ref is None) != (args.binding_file is None):
        parser.error("--binding-ref and --binding-file must be supplied together")
    report = inspect_deployment(args.root, args.binding_ref, args.binding_file)
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
