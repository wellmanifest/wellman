"""Dependency-free parser and validator for Lifecycle DSL v1."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CATALOG_SCHEMA = "lifecycle.diagnostics/v1"
REPORT_SCHEMA = "lifecycle.validation/v1"
SEVERITIES = {"INFO", "WARNING", "ERROR", "CRITICAL"}
IDENTIFIER = re.compile(r"^[A-Z][A-Z0-9_]*$")
LIFECYCLE_NAME = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
PROFILE_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+){2,}$")
CORE_CODE = re.compile(r"^LFC-[A-Z]+-[0-9]{3}$")
REQUIRED_CORE_CODES = {
    "LFC-IO-001",
    "LFC-SYNTAX-001",
    "LFC-SYNTAX-002",
    "LFC-DOC-001",
    "LFC-DOC-002",
    "LFC-MODEL-001",
    "LFC-MODEL-002",
    "LFC-MODEL-003",
    "LFC-MODEL-004",
    "LFC-MODEL-005",
    "LFC-MODEL-006",
    "LFC-MODEL-007",
    "LFC-ERROR-001",
    "LFC-ERROR-002",
    "LFC-ERROR-003",
    "LFC-CATALOG-001",
}
EMBEDDED_CATALOG_ROWS = (
    ("LFC-IO-001", "ERROR", "Lifecycle input could not be read."),
    ("LFC-SYNTAX-001", "ERROR", "Lifecycle input is not valid UTF-8."),
    ("LFC-SYNTAX-002", "ERROR", "Lifecycle statement syntax is invalid."),
    ("LFC-DOC-001", "ERROR", "Lifecycle document boundary is invalid."),
    ("LFC-DOC-002", "ERROR", "Lifecycle name is duplicated in the bundle."),
    ("LFC-MODEL-001", "ERROR", "Lifecycle identifier or scalar is invalid."),
    ("LFC-MODEL-002", "ERROR", "Lifecycle declaration is duplicated."),
    (
        "LFC-MODEL-003",
        "ERROR",
        "Lifecycle must declare exactly one initial state.",
    ),
    (
        "LFC-MODEL-004",
        "ERROR",
        "Lifecycle statement references an undeclared symbol.",
    ),
    (
        "LFC-MODEL-005",
        "ERROR",
        "State and event pair has more than one decision.",
    ),
    (
        "LFC-MODEL-006",
        "ERROR",
        "Lifecycle state is unreachable from the initial state.",
    ),
    ("LFC-MODEL-007", "ERROR", "Terminal state has an outgoing transition."),
    ("LFC-ERROR-001", "ERROR", "Profile error declaration is invalid."),
    (
        "LFC-ERROR-002",
        "ERROR",
        "Profile error binding is unresolved or unused.",
    ),
    (
        "LFC-ERROR-003",
        "ERROR",
        "Profile error code is duplicated in the bundle.",
    ),
    ("LFC-CATALOG-001", "CRITICAL", "Core diagnostic catalog is invalid."),
)


class CatalogError(RuntimeError):
    """The trusted core diagnostic catalog cannot be used."""


@dataclass(frozen=True)
class CatalogEntry:
    code: str
    severity: str
    message: str


def embedded_catalog() -> dict[str, CatalogEntry]:
    """Return the trusted catalog bundled with the standalone validator."""

    result = {
        code: CatalogEntry(code, severity, message)
        for code, severity, message in EMBEDDED_CATALOG_ROWS
    }
    if set(result) != REQUIRED_CORE_CODES:
        raise CatalogError("LFC-CATALOG-001: embedded diagnostic set is invalid")
    return result


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: str
    message: str
    path: str
    line: int
    document: str | None
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
            "line": self.line,
            "document": self.document,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class State:
    name: str
    initial: bool
    terminal: bool
    line: int


@dataclass(frozen=True)
class Transition:
    source: str
    target: str
    event: str
    evidence: str | None
    line: int


@dataclass(frozen=True)
class Reject:
    state: str
    event: str
    error: str
    line: int


@dataclass(frozen=True)
class ProfileError:
    code: str
    severity: str
    message: str
    line: int


AUDIT_SCHEMA = "lifecycle.compaction-audit/v1"


@dataclass
class Lifecycle:
    name: str
    version: int
    line: int
    description: str | None = None
    description_line: int = 0
    states: dict[str, State] = field(default_factory=dict)
    events: dict[str, int] = field(default_factory=dict)
    evidence: dict[str, int] = field(default_factory=dict)
    transitions: list[Transition] = field(default_factory=list)
    rejects: list[Reject] = field(default_factory=list)
    errors: dict[str, ProfileError] = field(default_factory=dict)
    uncompacted_states: list[State] = field(default_factory=list)
    uncompacted_events: list[str] = field(default_factory=list)
    uncompacted_evidence: list[str] = field(default_factory=list)
    uncompacted_transitions: list[Transition] = field(default_factory=list)
    uncompacted_rejects: list[Reject] = field(default_factory=list)
    batch_state_count: int = 0
    batch_event_count: int = 0
    batch_evidence_count: int = 0
    state_set_transition_count: int = 0
    state_set_reject_count: int = 0

    def summary(self) -> dict[str, Any]:
        initial = sorted(state.name for state in self.states.values() if state.initial)
        terminal = sorted(
            state.name for state in self.states.values() if state.terminal
        )
        return {
            "name": self.name,
            "version": self.version,
            "initial_state": initial[0] if len(initial) == 1 else None,
            "terminal_states": terminal,
            "state_count": len(self.states),
            "event_count": len(self.events),
            "evidence_count": len(self.evidence),
            "transition_count": len(self.transitions),
            "reject_count": len(self.rejects),
            "error_count": len(self.errors),
        }


@dataclass
class ValidationReport:
    source: str
    lifecycles: list[Lifecycle]
    diagnostics: list[Diagnostic]

    @property
    def valid(self) -> bool:
        return not self.diagnostics

    def as_dict(self) -> dict[str, Any]:
        ordered = sorted(
            self.diagnostics,
            key=lambda item: (item.line, item.code, item.document or "", item.detail),
        )
        return {
            "schema": REPORT_SCHEMA,
            "status": "valid" if self.valid else "invalid",
            "source": self.source,
            "lifecycle_count": len(self.lifecycles),
            "lifecycles": [item.summary() for item in self.lifecycles],
            "diagnostics": [item.as_dict() for item in ordered],
        }


def load_catalog(path: Path) -> dict[str, CatalogEntry]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CatalogError(f"LFC-CATALOG-001: cannot load {path}: {error}") from error
    if not isinstance(document, dict) or set(document) != {
        "schema",
        "version",
        "diagnostics",
    }:
        raise CatalogError("LFC-CATALOG-001: catalog fields are invalid")
    if document["schema"] != CATALOG_SCHEMA or document["version"] != 1:
        raise CatalogError("LFC-CATALOG-001: catalog schema or version is unsupported")
    rows = document["diagnostics"]
    if not isinstance(rows, list):
        raise CatalogError("LFC-CATALOG-001: diagnostics must be an array")
    result: dict[str, CatalogEntry] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"code", "severity", "message"}:
            raise CatalogError(
                f"LFC-CATALOG-001: diagnostic {index} fields are invalid"
            )
        code, severity, message = row["code"], row["severity"], row["message"]
        if (
            not isinstance(code, str)
            or CORE_CODE.fullmatch(code) is None
            or not isinstance(severity, str)
            or severity not in SEVERITIES
            or not isinstance(message, str)
            or not message.strip()
            or code in result
        ):
            raise CatalogError(f"LFC-CATALOG-001: diagnostic {index} is invalid")
        result[code] = CatalogEntry(code, severity, message)
    if set(result) != REQUIRED_CORE_CODES:
        missing = sorted(REQUIRED_CORE_CODES - set(result))
        extra = sorted(set(result) - REQUIRED_CORE_CODES)
        raise CatalogError(
            f"LFC-CATALOG-001: code set differs; missing={missing}, extra={extra}"
        )
    return result


class Emitter:
    def __init__(self, path: str, catalog: dict[str, CatalogEntry]) -> None:
        self.path = path
        self.catalog = catalog
        self.diagnostics: list[Diagnostic] = []

    def emit(
        self, code: str, line: int, detail: str, document: str | None = None
    ) -> None:
        try:
            entry = self.catalog[code]
        except KeyError as error:
            raise CatalogError(
                f"LFC-CATALOG-001: emitted unknown core code {code}"
            ) from error
        self.diagnostics.append(
            Diagnostic(
                code, entry.severity, entry.message, self.path, line, document, detail
            )
        )


def _tokens(text: str) -> list[str]:
    lexer = shlex.shlex(text, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    return list(lexer)


def _extract_bracketed_list(
    tokens: list[str], start_index: int
) -> tuple[list[str], int] | None:
    if start_index >= len(tokens) or not tokens[start_index].startswith("["):
        return None
    end_index = -1
    for idx in range(start_index, len(tokens)):
        if "]" in tokens[idx]:
            if not tokens[idx].endswith("]") or "[" in tokens[idx][1:]:
                return None
            end_index = idx
            break
        if idx > start_index and "[" in tokens[idx]:
            return None
    if end_index == -1:
        return None
    joined = " ".join(tokens[start_index : end_index + 1])
    inner = joined[1:-1].strip()
    if not inner:
        return None
    items: list[str] = []
    for raw_item in inner.split(","):
        item = raw_item.strip()
        if not item or any(ch.isspace() for ch in item):
            return None
        items.append(item)
    return items, end_index + 1


def _declare(
    values: dict[str, Any],
    name: str,
    value: Any,
    kind: str,
    line: int,
    model: Lifecycle,
    emitter: Emitter,
) -> None:
    if IDENTIFIER.fullmatch(name) is None:
        emitter.emit(
            "LFC-MODEL-001", line, f"invalid {kind} identifier {name!r}", model.name
        )
        return
    if name in values:
        emitter.emit("LFC-MODEL-002", line, f"duplicate {kind} {name}", model.name)
        return
    values[name] = value


def _parse_statement(
    tokens: list[str], line: int, model: Lifecycle, emitter: Emitter
) -> None:
    keyword = tokens[0]
    if keyword == "DESCRIPTION":
        if len(tokens) != 2 or not tokens[1].strip():
            emitter.emit(
                "LFC-SYNTAX-002",
                line,
                "DESCRIPTION requires one quoted value",
                model.name,
            )
        elif model.description is not None:
            emitter.emit("LFC-MODEL-002", line, "duplicate DESCRIPTION", model.name)
        else:
            model.description = tokens[1]
            model.description_line = line
        return
    if keyword == "STATE":
        modifiers = tokens[2:]
        if len(tokens) < 2 or any(
            item not in {"INITIAL", "TERMINAL"} for item in modifiers
        ):
            emitter.emit("LFC-SYNTAX-002", line, "STATE syntax is invalid", model.name)
            return
        if len(set(modifiers)) != len(modifiers):
            emitter.emit(
                "LFC-SYNTAX-002", line, "STATE modifiers must be unique", model.name
            )
            return
        state = State(tokens[1], "INITIAL" in modifiers, "TERMINAL" in modifiers, line)
        _declare(model.states, state.name, state, "state", line, model, emitter)
        model.uncompacted_states.append(state)
        return
    if keyword == "STATES":
        parsed = _extract_bracketed_list(tokens, 1)
        if parsed is None:
            emitter.emit("LFC-SYNTAX-002", line, "STATES syntax is invalid", model.name)
            return
        names, next_idx = parsed
        modifiers = tokens[next_idx:]
        if any(item not in {"INITIAL", "TERMINAL"} for item in modifiers):
            emitter.emit("LFC-SYNTAX-002", line, "STATES syntax is invalid", model.name)
            return
        if len(set(modifiers)) != len(modifiers):
            emitter.emit(
                "LFC-SYNTAX-002", line, "STATES modifiers must be unique", model.name
            )
            return
        for name in names:
            state = State(name, "INITIAL" in modifiers, "TERMINAL" in modifiers, line)
            _declare(model.states, state.name, state, "state", line, model, emitter)
            model.batch_state_count += 1
        return
    if keyword in {"EVENT", "EVIDENCE"}:
        if len(tokens) != 2:
            emitter.emit(
                "LFC-SYNTAX-002", line, f"{keyword} requires one identifier", model.name
            )
            return
        target = model.events if keyword == "EVENT" else model.evidence
        _declare(target, tokens[1], line, keyword.lower(), line, model, emitter)
        if keyword == "EVENT":
            model.uncompacted_events.append(tokens[1])
        else:
            model.uncompacted_evidence.append(tokens[1])
        return
    if keyword in {"EVENTS", "EVIDENCES"}:
        parsed = _extract_bracketed_list(tokens, 1)
        if parsed is None or parsed[1] != len(tokens):
            emitter.emit(
                "LFC-SYNTAX-002", line, f"{keyword} syntax is invalid", model.name
            )
            return
        names, _ = parsed
        target = model.events if keyword == "EVENTS" else model.evidence
        kind = "event" if keyword == "EVENTS" else "evidence"
        for name in names:
            _declare(target, name, line, kind, line, model, emitter)
            if keyword == "EVENTS":
                model.batch_event_count += 1
            else:
                model.batch_evidence_count += 1
        return
    if keyword == "TRANSITION":
        if len(tokens) >= 2 and tokens[1].startswith("["):
            parsed = _extract_bracketed_list(tokens, 1)
            if parsed is None:
                emitter.emit(
                    "LFC-SYNTAX-002", line, "TRANSITION syntax is invalid", model.name
                )
                return
            sources, next_idx = parsed
            rest = tokens[next_idx:]
            valid = (
                len(rest) in {4, 6}
                and rest[0] == "->"
                and rest[2] == "ON"
                and (len(rest) == 4 or rest[4] == "REQUIRES")
            )
            if not valid:
                emitter.emit(
                    "LFC-SYNTAX-002", line, "TRANSITION syntax is invalid", model.name
                )
                return
            target_state, event_name = rest[1], rest[3]
            if any(
                IDENTIFIER.fullmatch(item) is None
                for item in [*sources, target_state, event_name]
            ):
                emitter.emit(
                    "LFC-MODEL-001",
                    line,
                    "TRANSITION identifiers are invalid",
                    model.name,
                )
                return
            evidence = rest[5] if len(rest) == 6 else None
            if evidence is not None and IDENTIFIER.fullmatch(evidence) is None:
                emitter.emit(
                    "LFC-MODEL-001",
                    line,
                    "TRANSITION evidence identifier is invalid",
                    model.name,
                )
                return
            for source_state in sources:
                model.transitions.append(
                    Transition(source_state, target_state, event_name, evidence, line)
                )
                model.state_set_transition_count += 1
            return
        valid = len(tokens) in {6, 8} and tokens[2] == "->" and tokens[4] == "ON"
        valid = valid and (len(tokens) == 6 or tokens[6] == "REQUIRES")
        if not valid:
            emitter.emit(
                "LFC-SYNTAX-002", line, "TRANSITION syntax is invalid", model.name
            )
            return
        values = [tokens[1], tokens[3], tokens[5]]
        if any(IDENTIFIER.fullmatch(item) is None for item in values):
            emitter.emit(
                "LFC-MODEL-001", line, "TRANSITION identifiers are invalid", model.name
            )
            return
        evidence = tokens[7] if len(tokens) == 8 else None
        if evidence is not None and IDENTIFIER.fullmatch(evidence) is None:
            emitter.emit(
                "LFC-MODEL-001",
                line,
                "TRANSITION evidence identifier is invalid",
                model.name,
            )
            return
        transition = Transition(tokens[1], tokens[3], tokens[5], evidence, line)
        model.transitions.append(transition)
        model.uncompacted_transitions.append(transition)
        return
    if keyword == "REJECT":
        if len(tokens) >= 2 and tokens[1].startswith("["):
            parsed = _extract_bracketed_list(tokens, 1)
            if parsed is None:
                emitter.emit(
                    "LFC-SYNTAX-002", line, "REJECT syntax is invalid", model.name
                )
                return
            states, next_idx = parsed
            rest = tokens[next_idx:]
            if len(rest) != 4 or rest[0] != "ON" or rest[2] != "WITH":
                emitter.emit(
                    "LFC-SYNTAX-002", line, "REJECT syntax is invalid", model.name
                )
                return
            event_name, error_code = rest[1], rest[3]
            if any(
                IDENTIFIER.fullmatch(item) is None for item in [*states, event_name]
            ):
                emitter.emit(
                    "LFC-MODEL-001", line, "REJECT identifiers are invalid", model.name
                )
                return
            for state_name in states:
                model.rejects.append(Reject(state_name, event_name, error_code, line))
                model.state_set_reject_count += 1
            return
        if len(tokens) != 6 or tokens[2] != "ON" or tokens[4] != "WITH":
            emitter.emit("LFC-SYNTAX-002", line, "REJECT syntax is invalid", model.name)
            return
        if (
            IDENTIFIER.fullmatch(tokens[1]) is None
            or IDENTIFIER.fullmatch(tokens[3]) is None
        ):
            emitter.emit(
                "LFC-MODEL-001", line, "REJECT identifiers are invalid", model.name
            )
            return
        reject = Reject(tokens[1], tokens[3], tokens[5], line)
        model.rejects.append(reject)
        model.uncompacted_rejects.append(reject)
        return
    if keyword == "ERROR":
        if len(tokens) != 6 or tokens[2] != "SEVERITY" or tokens[4] != "MESSAGE":
            emitter.emit("LFC-SYNTAX-002", line, "ERROR syntax is invalid", model.name)
            return
        code, severity, message = tokens[1], tokens[3], tokens[5]
        if (
            PROFILE_ERROR_CODE.fullmatch(code) is None
            or code.startswith("LFC-")
            or severity not in SEVERITIES
            or not message.strip()
        ):
            emitter.emit(
                "LFC-ERROR-001", line, f"invalid profile error {code!r}", model.name
            )
            return
        if code in model.errors:
            emitter.emit("LFC-MODEL-002", line, f"duplicate error {code}", model.name)
            return
        model.errors[code] = ProfileError(code, severity, message, line)
        return
    emitter.emit("LFC-SYNTAX-002", line, f"unknown statement {keyword!r}", model.name)


def parse_bundle(text: str, emitter: Emitter) -> list[Lifecycle]:
    models: list[Lifecycle] = []
    current: Lifecycle | None = None
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        try:
            tokens = _tokens(raw_line)
        except ValueError as error:
            emitter.emit(
                "LFC-SYNTAX-002",
                line_number,
                f"tokenization failed: {error}",
                current.name if current else None,
            )
            continue
        if not tokens:
            continue
        if tokens[0] == "LIFECYCLE":
            if current is not None:
                emitter.emit(
                    "LFC-DOC-001", line_number, "new lifecycle before END", current.name
                )
                models.append(current)
            if len(tokens) != 4 or tokens[2] != "VERSION":
                emitter.emit(
                    "LFC-SYNTAX-002", line_number, "LIFECYCLE header is invalid"
                )
                current = None
                continue
            name = tokens[1]
            try:
                version = int(tokens[3])
            except ValueError:
                version = 0
            current = Lifecycle(name=name, version=version, line=line_number)
            if LIFECYCLE_NAME.fullmatch(name) is None or version != 1:
                emitter.emit(
                    "LFC-MODEL-001",
                    line_number,
                    f"invalid lifecycle name or unsupported version: {name!r} v{tokens[3]!r}",
                    name,
                )
            continue
        if tokens[0] == "END":
            if len(tokens) != 1 or current is None:
                emitter.emit(
                    "LFC-DOC-001", line_number, "END without one open lifecycle"
                )
            else:
                models.append(current)
                current = None
            continue
        if current is None:
            emitter.emit(
                "LFC-SYNTAX-002", line_number, "statement outside lifecycle document"
            )
            continue
        _parse_statement(tokens, line_number, current, emitter)
    if current is not None:
        emitter.emit(
            "LFC-DOC-001",
            current.line,
            "lifecycle reaches EOF without END",
            current.name,
        )
        models.append(current)
    if not models:
        emitter.emit("LFC-DOC-001", 0, "bundle contains no lifecycle document")
    seen_names: dict[str, int] = {}
    for model in models:
        if model.name in seen_names:
            emitter.emit(
                "LFC-DOC-002",
                model.line,
                f"lifecycle {model.name!r} first declared at line {seen_names[model.name]}",
                model.name,
            )
        else:
            seen_names[model.name] = model.line
    return models


def _check_reference(
    declared: dict[str, Any],
    value: str,
    kind: str,
    line: int,
    model: Lifecycle,
    emitter: Emitter,
) -> None:
    if value not in declared:
        emitter.emit("LFC-MODEL-004", line, f"undeclared {kind} {value}", model.name)


def _reachable(model: Lifecycle, initial: str) -> set[str]:
    edges: dict[str, set[str]] = {name: set() for name in model.states}
    for transition in model.transitions:
        if transition.source in edges and transition.target in model.states:
            edges[transition.source].add(transition.target)
    reached = {initial}
    queue = deque([initial])
    while queue:
        source = queue.popleft()
        for target in sorted(edges.get(source, ())):
            if target not in reached:
                reached.add(target)
                queue.append(target)
    return reached


def validate_models(models: Iterable[Lifecycle], emitter: Emitter) -> None:
    global_errors: dict[str, tuple[str, int]] = {}
    for model in models:
        initial_states = [state for state in model.states.values() if state.initial]
        if len(initial_states) != 1:
            emitter.emit(
                "LFC-MODEL-003",
                model.line,
                f"found {len(initial_states)} initial states",
                model.name,
            )

        for profile_error in model.errors.values():
            previous = global_errors.get(profile_error.code)
            if previous is not None:
                emitter.emit(
                    "LFC-ERROR-003",
                    profile_error.line,
                    f"{profile_error.code} first declared in {previous[0]} at line {previous[1]}",
                    model.name,
                )
            else:
                global_errors[profile_error.code] = (model.name, profile_error.line)

        decisions: dict[tuple[str, str], tuple[str, int]] = {}
        for kind, decision in sorted(
            [("transition", item) for item in model.transitions]
            + [("reject", item) for item in model.rejects],
            key=lambda item: item[1].line,
        ):
            decision_state = (
                decision.source if isinstance(decision, Transition) else decision.state
            )
            key = (decision_state, decision.event)
            previous = decisions.get(key)
            if previous is not None:
                emitter.emit(
                    "LFC-MODEL-005",
                    decision.line,
                    f"{decision_state}/{decision.event} already has {previous[0]} at line {previous[1]}",
                    model.name,
                )
            else:
                decisions[key] = (kind, decision.line)

        used_errors: set[str] = set()
        for transition in model.transitions:
            _check_reference(
                model.states,
                transition.source,
                "state",
                transition.line,
                model,
                emitter,
            )
            _check_reference(
                model.states,
                transition.target,
                "state",
                transition.line,
                model,
                emitter,
            )
            _check_reference(
                model.events, transition.event, "event", transition.line, model, emitter
            )
            if transition.evidence is not None:
                _check_reference(
                    model.evidence,
                    transition.evidence,
                    "evidence",
                    transition.line,
                    model,
                    emitter,
                )
            source = model.states.get(transition.source)
            if source is not None and source.terminal:
                emitter.emit(
                    "LFC-MODEL-007",
                    transition.line,
                    f"terminal state {source.name} transitions on {transition.event}",
                    model.name,
                )

        for reject in model.rejects:
            _check_reference(
                model.states, reject.state, "state", reject.line, model, emitter
            )
            _check_reference(
                model.events, reject.event, "event", reject.line, model, emitter
            )
            if reject.error not in model.errors:
                emitter.emit(
                    "LFC-ERROR-002",
                    reject.line,
                    f"reject references undeclared error {reject.error}",
                    model.name,
                )
            else:
                used_errors.add(reject.error)
        for code, profile_error in model.errors.items():
            if code not in used_errors:
                emitter.emit(
                    "LFC-ERROR-002",
                    profile_error.line,
                    f"declared error {code} is unused",
                    model.name,
                )

        if len(initial_states) == 1:
            reached = _reachable(model, initial_states[0].name)
            for candidate_state in sorted(
                model.states.values(), key=lambda item: (item.line, item.name)
            ):
                if candidate_state.name not in reached:
                    emitter.emit(
                        "LFC-MODEL-006",
                        candidate_state.line,
                        f"state {candidate_state.name} is unreachable from {initial_states[0].name}",
                        model.name,
                    )


def validate_text(
    text: str,
    *,
    source: str,
    catalog: dict[str, CatalogEntry],
) -> ValidationReport:
    emitter = Emitter(source, catalog)
    models = parse_bundle(text, emitter)
    validate_models(models, emitter)
    return ValidationReport(source, models, emitter.diagnostics)


def validate_path(path: Path, catalog: dict[str, CatalogEntry]) -> ValidationReport:
    emitter = Emitter(str(path), catalog)
    try:
        content = path.read_bytes()
    except OSError as error:
        emitter.emit("LFC-IO-001", 0, str(error))
        return ValidationReport(str(path), [], emitter.diagnostics)
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        emitter.emit("LFC-SYNTAX-001", 0, str(error))
        return ValidationReport(str(path), [], emitter.diagnostics)
    return validate_text(text, source=str(path), catalog=catalog)


def render_text(report: ValidationReport) -> str:
    if report.valid:
        lines = [
            (
                f"VALID {summary['name']} v{summary['version']} "
                f"states={summary['state_count']} events={summary['event_count']} "
                f"transitions={summary['transition_count']} rejects={summary['reject_count']}"
            )
            for summary in (item.summary() for item in report.lifecycles)
        ]
        lines.append(f"PASS {report.source}: {len(report.lifecycles)} lifecycle(s)")
        return "\n".join(lines)
    diagnostics = sorted(
        report.diagnostics,
        key=lambda item: (item.line, item.code, item.document or "", item.detail),
    )
    lines = [
        f"{item.path}:{item.line} {item.code} {item.severity}: {item.message} ({item.detail})"
        for item in diagnostics
    ]
    lines.append(f"FAIL {report.source}: {len(diagnostics)} diagnostic(s)")
    return "\n".join(lines)


def audit_compaction(
    text: str,
    *,
    source: str = "<memory>",
    catalog: dict[str, CatalogEntry] | None = None,
) -> dict[str, Any]:
    active_catalog = catalog if catalog is not None else embedded_catalog()
    report = validate_text(text, source=source, catalog=active_catalog)
    findings: list[dict[str, Any]] = []
    lifecycle_summaries: list[dict[str, Any]] = []
    for model in report.lifecycles:
        doc_findings: list[dict[str, Any]] = []
        plain_states = [
            state.name
            for state in model.uncompacted_states
            if not state.initial and not state.terminal
        ]
        if len(plain_states) >= 3:
            doc_findings.append(
                {
                    "code": "LFC-COMPACT-001",
                    "document": model.name,
                    "message": (
                        f"{len(plain_states)} plain STATE declarations can be "
                        "compacted into STATES [...]"
                    ),
                    "suggestion": f"STATES [{', '.join(plain_states)}]",
                    "estimated_lines_saved": len(plain_states) - 1,
                }
            )
        terminal_states = [
            state.name
            for state in model.uncompacted_states
            if not state.initial and state.terminal
        ]
        if len(terminal_states) >= 2:
            doc_findings.append(
                {
                    "code": "LFC-COMPACT-001",
                    "document": model.name,
                    "message": (
                        f"{len(terminal_states)} terminal STATE declarations can be "
                        "compacted into STATES [...] TERMINAL"
                    ),
                    "suggestion": f"STATES [{', '.join(terminal_states)}] TERMINAL",
                    "estimated_lines_saved": len(terminal_states) - 1,
                }
            )
        if len(model.uncompacted_events) >= 3:
            doc_findings.append(
                {
                    "code": "LFC-COMPACT-002",
                    "document": model.name,
                    "message": (
                        f"{len(model.uncompacted_events)} EVENT declarations can be "
                        "compacted into EVENTS [...]"
                    ),
                    "suggestion": f"EVENTS [{', '.join(model.uncompacted_events)}]",
                    "estimated_lines_saved": len(model.uncompacted_events) - 1,
                }
            )
        if len(model.uncompacted_evidence) >= 3:
            doc_findings.append(
                {
                    "code": "LFC-COMPACT-003",
                    "document": model.name,
                    "message": (
                        f"{len(model.uncompacted_evidence)} EVIDENCE declarations can "
                        "be compacted into EVIDENCES [...]"
                    ),
                    "suggestion": f"EVIDENCES [{', '.join(model.uncompacted_evidence)}]",
                    "estimated_lines_saved": len(model.uncompacted_evidence) - 1,
                }
            )
        transition_groups: dict[tuple[str, str, str | None], list[str]] = {}
        for transition in model.uncompacted_transitions:
            key = (transition.target, transition.event, transition.evidence)
            group = transition_groups.setdefault(key, [])
            if transition.source not in group:
                group.append(transition.source)
        for (target_state, event_name, evidence), sources in transition_groups.items():
            if len(sources) >= 2:
                requires_clause = f" REQUIRES {evidence}" if evidence else ""
                doc_findings.append(
                    {
                        "code": "LFC-COMPACT-004",
                        "document": model.name,
                        "message": (
                            f"{len(sources)} transitions into {target_state} on "
                            f"{event_name} share identical target/event/evidence"
                        ),
                        "suggestion": (
                            f"TRANSITION [{', '.join(sources)}] -> {target_state} "
                            f"ON {event_name}{requires_clause}"
                        ),
                        "estimated_lines_saved": len(sources) - 1,
                    }
                )
        reject_groups: dict[tuple[str, str], list[str]] = {}
        for reject in model.uncompacted_rejects:
            rkey = (reject.event, reject.error)
            rgroup = reject_groups.setdefault(rkey, [])
            if reject.state not in rgroup:
                rgroup.append(reject.state)
        for (event_name, error_code), states in reject_groups.items():
            if len(states) >= 2:
                doc_findings.append(
                    {
                        "code": "LFC-COMPACT-005",
                        "document": model.name,
                        "message": (
                            f"{len(states)} reject rules on {event_name} with "
                            f"{error_code} can be compacted"
                        ),
                        "suggestion": (
                            f"REJECT [{', '.join(states)}] ON {event_name} "
                            f"WITH {error_code}"
                        ),
                        "estimated_lines_saved": len(states) - 1,
                    }
                )
        findings.extend(doc_findings)
        lifecycle_summaries.append(
            {
                "name": model.name,
                "state_count": len(model.states),
                "event_count": len(model.events),
                "evidence_count": len(model.evidence),
                "transition_count": len(model.transitions),
                "reject_count": len(model.rejects),
                "batch_states": model.batch_state_count,
                "batch_events": model.batch_event_count,
                "batch_evidence": model.batch_evidence_count,
                "state_set_transitions": model.state_set_transition_count,
                "state_set_rejects": model.state_set_reject_count,
                "finding_count": len(doc_findings),
            }
        )
    return {
        "schema": AUDIT_SCHEMA,
        "source": source,
        "valid": report.valid,
        "lifecycle_count": len(report.lifecycles),
        "finding_count": len(findings),
        "estimated_lines_saved": sum(
            item["estimated_lines_saved"] for item in findings
        ),
        "lifecycles": lifecycle_summaries,
        "findings": findings,
    }


def audit_path(
    path: Path, catalog: dict[str, CatalogEntry] | None = None
) -> dict[str, Any]:
    active_catalog = catalog if catalog is not None else embedded_catalog()
    content = path.read_text(encoding="utf-8")
    return audit_compaction(content, source=str(path), catalog=active_catalog)


def render_audit_text(audit: dict[str, Any]) -> str:
    lines = [
        (
            f"AUDIT {audit['source']}: lifecycles={audit['lifecycle_count']} "
            f"findings={audit['finding_count']} "
            f"estimated_lines_saved={audit['estimated_lines_saved']}"
        )
    ]
    for finding in audit["findings"]:
        lines.append(
            f"- [{finding['code']}] {finding['document']}: {finding['message']} "
            f"=> {finding['suggestion']}"
        )
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lifecycle", description="Validate Lifecycle DSL v1"
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    validate = subcommands.add_parser("validate", help="validate one lifecycle bundle")
    validate.add_argument("path", type=Path)
    validate.add_argument("--format", choices=("text", "json"), default="text")
    validate.add_argument("--catalog", type=Path)
    audit = subcommands.add_parser(
        "audit", help="audit one lifecycle bundle for compaction opportunities"
    )
    audit.add_argument("path", type=Path)
    audit.add_argument("--format", choices=("text", "json"), default="text")
    audit.add_argument("--catalog", type=Path)
    return parser


def default_catalog_path() -> Path:
    return Path(__file__).resolve().parents[1] / "errors" / "catalog.json"


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        catalog = load_catalog(args.catalog) if args.catalog else embedded_catalog()
        if args.command == "audit":
            audit = audit_path(args.path, catalog)
            if args.format == "json":
                print(json.dumps(audit, indent=2, sort_keys=True))
            else:
                print(render_audit_text(audit))
            return 0 if audit["valid"] else 1
        report = validate_path(args.path, catalog)
        if args.format == "json":
            print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
        else:
            print(render_text(report))
        return 0 if report.valid else 1
    except CatalogError as error:
        print(str(error), file=sys.stderr)
        return 2
    except Exception as error:  # noqa: BLE001 - fail closed at the CLI trust boundary
        print(
            f"lifecycle internal error: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
