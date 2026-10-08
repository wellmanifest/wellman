"""Versioned, effect-free contracts for evidence-based standard selection.

These documents describe observations and proposals, never approval. The schema
interpreter supports only the assertions used by our bundled schemas; callers
cannot supply a schema, resolve a remote reference or execute a validator.
Canonical digests preserve array order. The planner must order decisions and
dependencies before hashing; a source digest must include relevant untracked
files, staged/unstaged contents, removals, manifests and adoption locks.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any


SCHEMAS = {
    "wellman.observation/v1": "observation.schema.json",
    "wellman.applicability-catalog/v1": "applicability-catalog.schema.json",
    "wellman.selection-plan/v1": "selection-plan.schema.json",
}
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
MAX_DEPTH = 64


class ContractError(ValueError):
    """Invalid or unsupported selection evidence; no effect is permitted."""


def canonical_bytes(value: Any) -> bytes:
    """Encode JSON deterministically without coercing keys or nonfinite numbers."""
    def check(node: Any, depth: int = 0) -> None:
        if depth > MAX_DEPTH:
            raise ContractError("JSON nesting exceeds the contract limit")
        if isinstance(node, dict):
            if any(not isinstance(key, str) for key in node):
                raise ContractError("JSON object keys must be strings")
            for item in node.values():
                check(item, depth + 1)
        elif isinstance(node, list):
            for item in node:
                check(item, depth + 1)
        elif node is not None and type(node) not in (str, int, float, bool):
            raise ContractError("Value is not JSON")
        elif isinstance(node, float) and not math.isfinite(node):
            raise ContractError("Nonfinite numbers are not evidence")
    check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def payload_digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _check(value: Any, rule: dict, root: dict, path: str = "$", depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise ContractError(f"{path}: schema nesting limit")
    if "$ref" in rule:
        ref = rule["$ref"]
        if not ref.startswith("#/$defs/"):
            raise ContractError("Only bundled local schema references are allowed")
        return _check(value, root["$defs"][ref.split("/")[-1]], root, path, depth + 1)
    types = rule.get("type", [])
    if isinstance(types, str):
        types = [types]
    matches = {
        "null": value is None, "object": isinstance(value, dict),
        "array": isinstance(value, list), "string": isinstance(value, str),
        "boolean": type(value) is bool, "integer": type(value) is int,
        "number": type(value) in (int, float),
    }
    if types and not any(matches.get(t, False) for t in types):
        raise ContractError(f"{path}: expected {types}")
    if "const" in rule and (type(value) is not type(rule["const"]) or value != rule["const"]):
        raise ContractError(f"{path}: invalid constant")
    if "enum" in rule and not any(type(value) is type(item) and value == item for item in rule["enum"]):
        raise ContractError(f"{path}: invalid enum")
    if isinstance(value, dict):
        props = rule.get("properties", {})
        missing = set(rule.get("required", [])) - value.keys()
        if missing:
            raise ContractError(f"{path}: missing {sorted(missing)}")
        if rule.get("additionalProperties") is False and value.keys() - props.keys():
            raise ContractError(f"{path}: unknown properties {sorted(value.keys() - props.keys())}")
        for key, item in value.items():
            sub = props.get(key, rule.get("additionalProperties"))
            if isinstance(sub, dict):
                _check(item, sub, root, f"{path}.{key}", depth + 1)
    elif isinstance(value, list):
        if len(value) < rule.get("minItems", 0) or len(value) > rule.get("maxItems", MAX_DOCUMENT_BYTES):
            raise ContractError(f"{path}: invalid array length")
        if rule.get("uniqueItems") and len({canonical_bytes(v) for v in value}) != len(value):
            raise ContractError(f"{path}: duplicate items")
        for index, item in enumerate(value):
            _check(item, rule.get("items", {}), root, f"{path}[{index}]", depth + 1)
    elif isinstance(value, str):
        if len(value) < rule.get("minLength", 0) or len(value) > rule.get("maxLength", MAX_DOCUMENT_BYTES):
            raise ContractError(f"{path}: invalid string length")
        if "pattern" in rule and re.search(rule["pattern"], value) is None:
            raise ContractError(f"{path}: invalid format")
    elif type(value) in (int, float):
        if value < rule.get("minimum", -math.inf) or value > rule.get("maximum", math.inf):
            raise ContractError(f"{path}: invalid number")


def validate_document(document: Any) -> dict:
    """Validate one known contract; incomplete observations remain incomplete."""
    if (not isinstance(document, dict) or not isinstance(document.get("schema"), str)
            or document["schema"] not in SCHEMAS):
        raise ContractError("Unknown selection contract schema")
    if len(canonical_bytes(document)) > MAX_DOCUMENT_BYTES:
        raise ContractError("Selection document exceeds the size limit")
    schema = json.loads((Path(__file__).parent / "schemas" / SCHEMAS[document["schema"]]).read_text())
    _check(document, schema, schema)
    if document["schema"] == "wellman.observation/v1":
        for stage in document["stages"]:
            if stage["status"] == "complete" and (stage["truncated"] or stage["exit_code"] != 0):
                raise ContractError("A complete stage cannot be truncated or failed")
        for feature in document["features"]:
            if feature["state"] != "unknown" and not feature["evidence_refs"]:
                raise ContractError("Known feature requires evidence references")
            if feature["state"] == "absent" and feature["coverage"] != "complete":
                raise ContractError("Absent feature requires complete coverage")
    return document


def plan_digest(plan: dict) -> str:
    """Bind all material inputs; exclude only the hash and rendering metadata."""
    validate_document(plan)
    if plan["schema"] != "wellman.selection-plan/v1":
        raise ContractError("Expected a selection plan")
    return payload_digest({key: value for key, value in plan.items()
                           if key not in {"plan_hash", "rendered_at", "output_path"}})
