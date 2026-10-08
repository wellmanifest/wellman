"""Bounded runtime feedback from pinned JSON contracts; no repair execution.

An event hash establishes integrity, not producer identity, source freshness or
successful remediation. Recommendations are review candidates. They never
become capability evidence or grant adoption, shell, URI or LLM authority.
Run this module repeatedly on an explicit stream to retain stable group IDs.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

from wellman.evidence import _json
from wellman.registry import STANDARDS_CATALOG
from wellman.selection_contracts import (
    ContractError, MAX_DEPTH, MAX_DOCUMENT_BYTES, _check,
    canonical_bytes, payload_digest,
)

VERSION = "wellman.runtime-feedback/v1"


def _time(value):
    if not isinstance(value, str):
        raise ContractError("A timezone-aware timestamp is required")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError("Invalid timestamp") from error
    if result.tzinfo is None:
        raise ContractError("A timezone-aware timestamp is required")
    return result


def _validate(value, rule, root, depth=0):
    """Closed, data-only subset of JSON Schema used by the pinned logs schema."""
    supported = {"$schema", "$id", "$defs", "$ref", "title", "description",
                 "type", "required", "properties", "additionalProperties",
                 "items", "minItems", "maxItems", "uniqueItems", "const",
                 "enum", "minLength", "maxLength", "pattern", "minimum",
                 "maximum", "oneOf", "format"}
    if depth > MAX_DEPTH or not isinstance(rule, dict) or set(rule) - supported:
        raise ContractError("Unsupported or recursive logs schema")
    if "$ref" in rule:
        ref = rule["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
            raise ContractError("Only local schema references are supported")
        target = root.get("$defs", {}).get(ref[len("#/$defs/"):])
        if target is None:
            raise ContractError("Missing local schema definition")
        return _validate(value, target, root, depth + 1)
    if "oneOf" in rule:
        matches = 0
        for variant in rule["oneOf"]:
            try:
                _validate(value, variant, root, depth + 1)
                matches += 1
            except ContractError:
                pass
        if matches != 1:
            raise ContractError("Event does not match exactly one schema variant")
    # Scalar/container assertions, followed by recursion including union rules.
    shallow = {k: v for k, v in rule.items() if k not in {"items", "properties"}}
    if "properties" in rule:
        shallow["properties"] = {k: {} for k in rule["properties"]}
    _check(value, shallow, shallow)
    if rule.get("format"):
        if rule["format"] != "date-time":
            raise ContractError("Unsupported schema format")
        _time(value)
    if isinstance(value, dict):
        for key, item in value.items():
            sub = rule.get("properties", {}).get(key, rule.get("additionalProperties"))
            if isinstance(sub, dict):
                _validate(item, sub, root, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _validate(item, rule.get("items", {}), root, depth + 1)


def _rules(rules):
    if not isinstance(rules, dict):
        raise ContractError("Rules must map exact diagnostic codes to standard IDs")
    for code, standards in rules.items():
        if (not isinstance(code, str)
                or not re.fullmatch(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+", code)
                or not isinstance(standards, list) or not standards
                or any(not isinstance(s, str) or s not in STANDARDS_CATALOG for s in standards)
                or len(standards) != len(set(standards))):
            raise ContractError("Unknown diagnostic code or standard in routing rules")


def analyze_events(raw, *, contract, contract_sha256, rules, stream,
                   subject_prefix, window_start, window_end):
    """Summarize one explicitly scoped stream without trusting repair claims.

    Validate every line before applying the time window, so old corruption is
    visible. The first retained chain segment is an unverified anchor; later
    events must chain consecutively. A replay of identical event bytes is
    counted once. Conflicting IDs and broken chains stop further ingestion.
    Invalid lines give partial coverage, never proof that errors are absent.
    The caller supplies trusted routing policy and an independently pinned
    contract digest. Neither policy nor event text is executed.
    """
    if not isinstance(raw, bytes) or not isinstance(contract, bytes):
        raise ContractError("Inputs must be bytes")
    if max(len(raw), len(contract)) > MAX_DOCUMENT_BYTES:
        raise ContractError("Feedback input exceeds the bounded document limit")
    if hashlib.sha256(contract).hexdigest() != contract_sha256:
        raise ContractError("Pinned logs contract digest mismatch")
    bundle = _json(contract)
    if bundle.get("schema") != "wellmanifest.logs/contract-bundle/v1":
        raise ContractError("Unknown logs contract")
    schemas = bundle.get("schemas")
    schema = schemas.get("event") if isinstance(schemas, dict) else None
    if not isinstance(schema, dict):
        raise ContractError("Logs contract lacks an event schema")
    consumed = {"eventId", "eventHash", "previousHash", "sequence", "source",
                "subjectRef", "stream", "occurredAt", "outcome", "severity",
                "eventType", "code", "causationId", "correlationId",
                "rawOutputIncluded", "secretMaterialIncluded", "schema"}
    properties = schema.get("properties")
    if (schema.get("type") != "object"
            or not isinstance(properties, dict)
            or not isinstance(properties.get("schema"), dict)
            or not isinstance(schema.get("required"), list)
            or schema.get("additionalProperties") is not False
            or not consumed.issubset(schema.get("required", []))
            or properties["schema"].get("const")
            != "wellmanifest.logs/event/v1"):
        raise ContractError("Logs schema must retain the closed v1 event envelope")
    _rules(rules)
    if not isinstance(stream, str) or not re.fullmatch(r"[a-z][a-z0-9._-]{0,63}", stream):
        raise ContractError("An explicit stream is required")
    if (not isinstance(subject_prefix, str)
            or not re.fullmatch(r"[a-z][a-z0-9+.-]*:[A-Za-z0-9._:/-]+", subject_prefix)):
        raise ContractError("An explicit subject URI prefix is required")
    start, end = _time(window_start), _time(window_end)
    if start >= end:
        raise ContractError("Invalid observation window")
    diagnostics, seen, events = [], {}, []
    previous = None
    duplicates = outside = foreign = 0
    latest_scoped_event = None
    for number, line in enumerate(raw.splitlines(keepends=True), 1):
        try:
            if not line.endswith(b"\n"):
                raise ContractError("Incomplete line")
            event = _json(line)
            _validate(event, schema, schema)
            if any(not isinstance(event[k], str) for k in consumed - {
                    "sequence", "code", "causationId", "rawOutputIncluded", "secretMaterialIncluded"}):
                raise ContractError("Invalid event envelope types")
            if (type(event["sequence"]) is not int
                    or event["code"] is not None and not isinstance(event["code"], str)
                    or event["causationId"] is not None and not isinstance(event["causationId"], str)):
                raise ContractError("Invalid event envelope types")
            if canonical_bytes(event) + b"\n" != line:
                raise ContractError("Noncanonical event")
            if event.get("rawOutputIncluded") is not False or event.get("secretMaterialIncluded") is not False:
                raise ContractError("Unsafe payload declaration")
            if payload_digest({k: v for k, v in event.items() if k != "eventHash"}) != event.get("eventHash"):
                raise ContractError("Event hash mismatch")
        except (ValueError, UnicodeError, RecursionError):
            # Never echo parser exceptions, raw lines or unknown event values.
            diagnostics.append({"code": "RUNTIME-EVENT-INVALID", "line": number})
            continue
        identity = event["eventId"]
        if identity in seen:
            if seen[identity] == event["eventHash"]:
                duplicates += 1
                continue
            diagnostics.append({"code": "RUNTIME-EVENT-ID-CONFLICT", "line": number})
            break
        seen[identity] = event["eventHash"]
        if event["stream"] != stream:
            diagnostics.append({"code": "RUNTIME-STREAM-MISMATCH", "line": number})
            break
        if previous and (event["sequence"] != previous["sequence"] + 1
                         or event["previousHash"] != previous["eventHash"]):
            diagnostics.append({"code": "RUNTIME-CHAIN-BROKEN", "line": number})
            break
        previous = event
        if not event["subjectRef"].startswith(subject_prefix):
            foreign += 1
            continue
        stamp = _time(event["occurredAt"])
        if latest_scoped_event is None or stamp > _time(latest_scoped_event):
            latest_scoped_event = event["occurredAt"]
        if not start <= stamp <= end:
            outside += 1
            continue
        events.append(event)

    grouped = defaultdict(list)
    failures = {}
    for event in events:
        if (event["outcome"] == "FAILED"
                or event["severity"] in {"ERROR", "CRITICAL"}
                or event["eventType"] in {"error_raised", "validation_failed"}):
            grouped[(event["source"], event["subjectRef"], event["code"])].append(event)
            failures[event["eventId"]] = event
    groups = []
    for (source, subject, code), occurrences in grouped.items():
        refs = {e["eventId"] for e in occurrences}
        attempts = [e for e in events if e["eventType"] == "remediation_completed"
                    and e["causationId"] in refs
                    and e["correlationId"] == failures[e["causationId"]]["correlationId"]
                    and e["subjectRef"] == subject and e["source"] == source
                    and _time(e["occurredAt"]) >= _time(failures[e["causationId"]]["occurredAt"])]
        latest_attempt = max((_time(e["occurredAt"]) for e in attempts), default=None)
        recurrence = bool(latest_attempt and any(_time(e["occurredAt"]) > latest_attempt for e in occurrences))
        key = {"source": source, "subjectRef": subject, "code": code}
        groups.append({
            "id": "runtime-error:" + payload_digest(key), **key,
            "count": len(occurrences), "eventIds": sorted(refs),
            "firstSeen": min(occurrences, key=lambda e: _time(e["occurredAt"]))["occurredAt"],
            "lastSeen": max(occurrences, key=lambda e: _time(e["occurredAt"]))["occurredAt"],
            "remediationAttempts": len(attempts), "recurrenceAfterAttempt": recurrence,
            "verification": "unverified", "priority": "recurring" if len(occurrences) > 1 else "single",
            "standardCandidates": sorted(rules.get(code, [])),
            "nextAction": "Review evidence and create a governed remediation ticket; verify the postcondition before closing.",
        })
    report = {
        "schema": VERSION, "stream": stream, "subjectPrefix": subject_prefix,
        "window": {"start": window_start, "end": window_end},
        "inputSha256": hashlib.sha256(raw).hexdigest(), "contractSha256": contract_sha256,
        "rulesDigest": payload_digest(rules), "coverage": "partial" if diagnostics else "observed-window",
        "observedEvents": len(events), "uniqueFailures": len(failures),
        "duplicateEvents": duplicates, "outsideWindow": outside, "outsideSubject": foreign,
        "latestScopedEventAt": latest_scoped_event,
        "activity": "events-in-window" if events else "no-events-in-window",
        "groups": sorted(groups, key=lambda g: (-g["count"], g["id"])),
        "unclassifiedFailures": sum(g["count"] for g in groups if not g["standardCandidates"]),
        "diagnostics": diagnostics, "grantsAuthority": False, "executable": False,
        "conformance": "unverified", "limitations": [
            "Windowed log observations do not prove absence of failures.",
            "Hashes do not authenticate producers or bind events to the current source revision.",
            "The first chain anchor and runtime postconditions are unverified.",
            "Candidate standards require independent capability, adoption and policy review.",
            "This is structural feedback, not full logs-domain conformance or remediation execution.",
        ],
    }
    report["reportDigest"] = payload_digest(report)
    return report


def _read(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ContractError("Input must be a regular file without symlink traversal")
    with path.open("rb") as handle:
        raw = handle.read(MAX_DOCUMENT_BYTES + 1)
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ContractError("Input exceeds the bounded document limit")
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--rules", required=True, help="JSON object mapping exact error codes to registered standard IDs")
    parser.add_argument("--stream", required=True)
    parser.add_argument("--subject-prefix", required=True)
    parser.add_argument("--since-hours", type=float, default=1)
    parser.add_argument("--end", help="Explicit timezone-aware end of window; defaults to now")
    args = parser.parse_args(argv)
    try:
        if not 0 < args.since_hours <= 168:
            raise ContractError("Observation window must be between zero and 168 hours")
        end = _time(args.end) if args.end else datetime.now(timezone.utc)
        result = analyze_events(
            _read(args.events), contract=_read(args.contract),
            contract_sha256=args.contract_sha256, rules=_json(_read(args.rules)),
            stream=args.stream, subject_prefix=args.subject_prefix,
            window_start=(end - timedelta(hours=args.since_hours)).isoformat(),
            window_end=end.isoformat(),
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1 if result["diagnostics"] else 0
    except (OSError, ValueError, RecursionError):
        print("Runtime feedback refused invalid, unavailable or oversized input.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
