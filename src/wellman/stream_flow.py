"""Wellmanifest Stream Flow, Decision Routing & Prioritized Dependency Engine (REUSE-015..018)."""

from __future__ import annotations

import ast
import hashlib
import heapq
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Generic, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple, TypeVar

T = TypeVar("T")

STREAM_FLOW_SCHEMA = "wellmanifest.stream-flow/v1"
STREAM_RECEIPT_SCHEMA = "wellmanifest.stream-flow-receipt/v1"

PRIORITY_TIERS: Tuple[str, ...] = ("floor", "standard", "opportunistic")
TIER_RANK: Dict[str, int] = {name: idx for idx, name in enumerate(PRIORITY_TIERS)}
STAGE_KINDS: Tuple[str, ...] = ("module", "component", "process")

_SKIP_DIRS = {
    ".git", ".governance", ".koru", ".mypy_cache", ".planfile", ".pytest_cache",
    ".ruff_cache", ".subactor", ".venv", ".worktrees", "__pycache__", "_bundled",
    "build", "dist", "node_modules", "target", "venv",
}
_STDLIB_NAMES: frozenset[str] = getattr(sys, "stdlib_module_names", frozenset()) | {"__future__", "typing_extensions"}


def tier_sort_key(tier: str, weight: float, identifier: str) -> Tuple[int, float, str]:
    """Return deterministic lexicographic sort key: lower tier rank first, higher weight first."""
    if tier not in TIER_RANK:
        raise ValueError(f"Unknown priority tier: {tier!r} (expected one of {PRIORITY_TIERS})")
    return (TIER_RANK[tier], -float(weight), str(identifier))


def canonical_digest(payload: Any) -> str:
    """Compute sha256:<hex> digest of canonical JSON representation."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class DecisionRule:
    """A single declarative decision rule evaluated in lexicographic priority order (REUSE-016)."""

    id: str
    tier: str
    weight: float
    outcome: str
    when: Optional[Callable[[Mapping[str, Any]], bool]] = None
    satisfied_when: Optional[Callable[[Mapping[str, Any]], bool]] = None
    handler: Optional[Callable[[Mapping[str, Any]], Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def sort_key(self) -> Tuple[int, float, str]:
        return tier_sort_key(self.tier, self.weight, self.id)


@dataclass(frozen=True)
class DecisionTrace:
    """Deterministic explanation of a decision evaluation."""

    selected_id: Optional[str]
    outcome: Optional[str]
    tier: Optional[str]
    weight: Optional[float]
    evaluated: Tuple[Dict[str, Any], ...]
    result: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_id": self.selected_id,
            "outcome": self.outcome,
            "tier": self.tier,
            "weight": self.weight,
            "evaluated": list(self.evaluated),
        }


class DecisionEngine:
    """Evaluates declarative DecisionRules in lexicographic (tier, -weight, id) order."""

    def __init__(self, rules: Iterable[DecisionRule], default_outcome: Optional[str] = None) -> None:
        rule_list = list(rules)
        ids = [r.id for r in rule_list]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate DecisionRule id detected")
        self._rules: List[DecisionRule] = sorted(rule_list, key=lambda r: r.sort_key())
        self.default_outcome = default_outcome

    @property
    def rules(self) -> Tuple[DecisionRule, ...]:
        return tuple(self._rules)

    def decide(self, context: Mapping[str, Any]) -> DecisionTrace:
        evaluated: List[Dict[str, Any]] = []
        for rule in self._rules:
            if rule.satisfied_when is not None and bool(rule.satisfied_when(context)):
                evaluated.append({"id": rule.id, "status": "already_satisfied", "tier": rule.tier, "weight": rule.weight})
                continue
            matched = True if rule.when is None else bool(rule.when(context))
            evaluated.append({"id": rule.id, "status": "matched" if matched else "skipped", "tier": rule.tier, "weight": rule.weight})
            if matched:
                res = rule.handler(context) if rule.handler is not None else rule.outcome
                return DecisionTrace(
                    selected_id=rule.id,
                    outcome=rule.outcome,
                    tier=rule.tier,
                    weight=rule.weight,
                    evaluated=tuple(evaluated),
                    result=res,
                )
        return DecisionTrace(
            selected_id=None,
            outcome=self.default_outcome,
            tier=None,
            weight=None,
            evaluated=tuple(evaluated),
            result=self.default_outcome,
        )


@dataclass(frozen=True)
class PrioritizedDependency(Generic[T]):
    """A provider candidate for a capability with lexicographic priority and readiness probe (REUSE-017)."""

    id: str
    capability: str
    tier: str
    weight: float
    provider: Callable[..., T]
    readiness_probe: Optional[Callable[[], bool]] = None
    fallback_id: Optional[str] = None

    def sort_key(self) -> Tuple[int, float, str]:
        return tier_sort_key(self.tier, self.weight, self.id)


@dataclass(frozen=True)
class DependencyResolution(Generic[T]):
    """Result of resolving a capability through a prioritized provider chain."""

    capability: str
    selected_id: str
    tier: str
    weight: float
    value: T
    attempted: Tuple[Dict[str, Any], ...]


class DependencyResolver:
    """Resolves capabilities across prioritized providers with automatic fallback."""

    def __init__(self, dependencies: Iterable[PrioritizedDependency[Any]] = ()) -> None:
        self._by_id: Dict[str, PrioritizedDependency[Any]] = {}
        self._by_cap: Dict[str, List[PrioritizedDependency[Any]]] = {}
        for dep in dependencies:
            self.register(dep)

    def register(self, dep: PrioritizedDependency[Any]) -> None:
        if dep.id in self._by_id:
            raise ValueError(f"Duplicate dependency id: {dep.id!r}")
        self._by_id[dep.id] = dep
        bucket = self._by_cap.setdefault(dep.capability, [])
        bucket.append(dep)
        bucket.sort(key=lambda d: d.sort_key())

    def resolve(self, capability: str, *args: Any, **kwargs: Any) -> DependencyResolution[Any]:
        candidates = list(self._by_cap.get(capability, ()))
        if not candidates:
            raise LookupError(f"No registered providers for capability: {capability!r}")

        ordered: List[PrioritizedDependency[Any]] = []
        visited: set[str] = set()
        for cand in candidates:
            cur: Optional[PrioritizedDependency[Any]] = cand
            while cur is not None and cur.id not in visited:
                visited.add(cur.id)
                ordered.append(cur)
                cur = self._by_id.get(cur.fallback_id) if cur.fallback_id else None

        attempted: List[Dict[str, Any]] = []
        last_error: Optional[Exception] = None
        for dep in ordered:
            ready = True
            if dep.readiness_probe is not None:
                try:
                    ready = bool(dep.readiness_probe())
                except Exception as exc:
                    ready = False
                    last_error = exc
            if not ready:
                attempted.append({"id": dep.id, "tier": dep.tier, "weight": dep.weight, "status": "unready"})
                continue
            try:
                val = dep.provider(*args, **kwargs)
                attempted.append({"id": dep.id, "tier": dep.tier, "weight": dep.weight, "status": "selected"})
                return DependencyResolution(
                    capability=capability,
                    selected_id=dep.id,
                    tier=dep.tier,
                    weight=dep.weight,
                    value=val,
                    attempted=tuple(attempted),
                )
            except Exception as exc:
                last_error = exc
                attempted.append({"id": dep.id, "tier": dep.tier, "weight": dep.weight, "status": "failed", "error": str(exc)})
        raise RuntimeError(f"All providers failed for capability {capability!r}: {last_error}")


@dataclass(frozen=True)
class StreamEnvelope(Generic[T]):
    """Immutable envelope flowing lazily through module, component, and process stages (REUSE-018)."""

    id: str
    payload: T
    stage: str = "ingress"
    kind: str = "module"
    meta: Dict[str, Any] = field(default_factory=dict)
    decisions: Tuple[Dict[str, Any], ...] = ()
    trace: Tuple[Dict[str, Any], ...] = ()

    def advance(
        self,
        *,
        stage: str,
        kind: str,
        payload: Any,
        tier: str,
        weight: float,
        status: str = "applied",
        decision: Optional[Dict[str, Any]] = None,
        extra_meta: Optional[Mapping[str, Any]] = None,
    ) -> "StreamEnvelope[Any]":
        merged_meta = dict(self.meta)
        if extra_meta:
            merged_meta.update(extra_meta)
        next_decisions = self.decisions + ((decision,) if decision else ())
        hop = {"stage": stage, "kind": kind, "tier": tier, "weight": weight, "status": status}
        return StreamEnvelope(
            id=self.id,
            payload=payload,
            stage=stage,
            kind=kind,
            meta=merged_meta,
            decisions=next_decisions,
            trace=self.trace + (hop,),
        )


@dataclass(frozen=True)
class StreamStage:
    """A structural unit (module, component, or process) in a prioritized stream pipeline."""

    id: str
    kind: str
    tier: str
    weight: float
    transform: Callable[[StreamEnvelope[Any]], Any]
    depends_on: Tuple[str, ...] = ()
    when: Optional[Callable[[StreamEnvelope[Any]], bool]] = None
    fallback: Optional[Callable[[StreamEnvelope[Any], Exception], Any]] = None
    decision_engine: Optional[DecisionEngine] = None

    def __post_init__(self) -> None:
        if self.kind not in STAGE_KINDS:
            raise ValueError(f"Invalid stage kind {self.kind!r}; expected one of {STAGE_KINDS}")
        tier_sort_key(self.tier, self.weight, self.id)

    def sort_key(self) -> Tuple[int, float, str]:
        return tier_sort_key(self.tier, self.weight, self.id)


@dataclass(frozen=True)
class StreamReceipt:
    """Tamper-evident execution receipt for a prioritized stream pipeline."""

    pipeline_id: str
    ordered_stages: Tuple[Dict[str, Any], ...]
    processed_count: int
    stage_counts: Dict[str, int]
    digest: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": STREAM_RECEIPT_SCHEMA,
            "pipeline_id": self.pipeline_id,
            "ordered_stages": list(self.ordered_stages),
            "processed_count": self.processed_count,
            "stage_counts": dict(self.stage_counts),
            "digest": self.digest,
        }


class StreamPipeline:
    """Composes modules, components, and processes into a prioritized, lazy generator stream."""

    def __init__(self, pipeline_id: str, stages: Iterable[StreamStage]) -> None:
        self.pipeline_id = pipeline_id
        stage_list = list(stages)
        if not stage_list:
            raise ValueError("StreamPipeline requires at least one StreamStage")
        by_id: Dict[str, StreamStage] = {}
        for st in stage_list:
            if st.id in by_id:
                raise ValueError(f"Duplicate stage id: {st.id!r}")
            by_id[st.id] = st
        self._stages_by_id = by_id
        self._ordered_stages = self._prioritized_topological_order(stage_list)
        self.last_receipt: Optional[StreamReceipt] = None

    @staticmethod
    def _prioritized_topological_order(stages: Sequence[StreamStage]) -> Tuple[StreamStage, ...]:
        by_id = {s.id: s for s in stages}
        indegree: Dict[str, int] = {s.id: 0 for s in stages}
        dependents: Dict[str, List[str]] = {s.id: [] for s in stages}
        for s in stages:
            for dep in s.depends_on:
                if dep not in by_id:
                    raise ValueError(f"Stage {s.id!r} depends on unknown stage {dep!r}")
                if dep == s.id:
                    raise ValueError(f"Stage {s.id!r} cannot depend on itself")
                indegree[s.id] += 1
                dependents[dep].append(s.id)

        heap: List[Tuple[Tuple[int, float, str], str]] = [
            (s.sort_key(), s.id) for s in stages if indegree[s.id] == 0
        ]
        heapq.heapify(heap)
        ordered: List[StreamStage] = []
        while heap:
            _, sid = heapq.heappop(heap)
            ordered.append(by_id[sid])
            for nxt in dependents[sid]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    heapq.heappush(heap, (by_id[nxt].sort_key(), nxt))

        if len(ordered) != len(stages):
            raise ValueError("Cycle detected in StreamPipeline stage dependencies")
        return tuple(ordered)

    @property
    def ordered_stages(self) -> Tuple[StreamStage, ...]:
        return self._ordered_stages

    def stream(self, items: Iterable[Any]) -> Iterator[StreamEnvelope[Any]]:
        """Lazily stream items through all ordered stages, yielding StreamEnvelopes one by one."""
        stage_counts: Dict[str, int] = {s.id: 0 for s in self._ordered_stages}
        processed = 0

        def _ensure_envelopes(source: Iterable[Any]) -> Iterator[StreamEnvelope[Any]]:
            for idx, item in enumerate(source):
                yield item if isinstance(item, StreamEnvelope) else StreamEnvelope(id=f"{self.pipeline_id}:{idx}", payload=item)

        def _apply_stage(upstream: Iterator[StreamEnvelope[Any]], stage: StreamStage) -> Iterator[StreamEnvelope[Any]]:
            for env in upstream:
                decision_dict: Optional[Dict[str, Any]] = None
                if stage.decision_engine is not None:
                    decision_dict = stage.decision_engine.decide({"id": env.id, "payload": env.payload, "meta": env.meta}).to_dict()
                if stage.when is not None and not bool(stage.when(env)):
                    yield env.advance(stage=stage.id, kind=stage.kind, payload=env.payload, tier=stage.tier, weight=stage.weight, status="skipped", decision=decision_dict)
                    continue
                try:
                    out = stage.transform(env)
                    status = "applied"
                except Exception as exc:
                    if stage.fallback is None:
                        raise
                    out = stage.fallback(env, exc)
                    status = "fallback"
                stage_counts[stage.id] += 1
                yield out if isinstance(out, StreamEnvelope) else env.advance(stage=stage.id, kind=stage.kind, payload=out, tier=stage.tier, weight=stage.weight, status=status, decision=decision_dict)

        current = _ensure_envelopes(items)
        for st in self._ordered_stages:
            current = _apply_stage(current, st)

        for final_env in current:
            processed += 1
            yield final_env

        stage_descriptors = tuple(
            {"id": s.id, "kind": s.kind, "tier": s.tier, "weight": s.weight, "depends_on": list(s.depends_on)}
            for s in self._ordered_stages
        )
        body = {
            "pipeline_id": self.pipeline_id,
            "ordered_stages": list(stage_descriptors),
            "processed_count": processed,
            "stage_counts": stage_counts,
        }
        self.last_receipt = StreamReceipt(
            pipeline_id=self.pipeline_id,
            ordered_stages=stage_descriptors,
            processed_count=processed,
            stage_counts=stage_counts,
            digest=canonical_digest(body),
        )


def _if_chain_length(node: ast.If) -> int:
    arms = 1
    cur: Optional[ast.If] = node
    while cur is not None and len(cur.orelse) == 1 and isinstance(cur.orelse[0], ast.If):
        arms += 1
        cur = cur.orelse[0]
    if cur is not None and cur.orelse:
        arms += 1
    return arms


def analyze_horizontal_complexity(
    project_root: Path,
    *,
    max_branch_arms: int = 5,
    max_fan_out: int = 12,
    max_file_lines: int = 500,
    include_tests: bool = False,
) -> Dict[str, Any]:
    """Scan Python modules for horizontal complexity hotspots (REUSE-015)."""
    root = project_root.resolve()
    hotspots: List[Dict[str, Any]] = []
    scanned_files = 0
    skip_dirs = set(_SKIP_DIRS)
    if not include_tests:
        skip_dirs.update({"test", "tests", "examples"})

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in skip_dirs and not d.startswith("."))
        for fname in sorted(filenames):
            if not fname.endswith(".py"):
                continue
            fpath = Path(dirpath) / fname
            if fpath.is_symlink():
                continue
            rel = fpath.relative_to(root).as_posix()
            try:
                source = fpath.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=rel)
            except (OSError, UnicodeError, SyntaxError):
                continue
            scanned_files += 1
            lines_count = len(source.splitlines())
            if lines_count > max_file_lines:
                hotspots.append({
                    "code": "REUSE-015-MONOLITH",
                    "path": rel,
                    "line": 1,
                    "metric": lines_count,
                    "limit": max_file_lines,
                    "remediation": "Split module into focused stages/facades (REUSE-011, REUSE-018).",
                })

            peer_imports: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        if top not in _STDLIB_NAMES:
                            peer_imports.add(alias.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    top = node.module.split(".")[0]
                    if node.level > 0 or top not in _STDLIB_NAMES:
                        peer_imports.add(node.module)
            if len(peer_imports) > max_fan_out:
                hotspots.append({
                    "code": "REUSE-015-FANOUT",
                    "path": rel,
                    "line": 1,
                    "metric": len(peer_imports),
                    "limit": max_fan_out,
                    "remediation": "Reduce horizontal peer imports using DependencyResolver or StreamPipeline (REUSE-017, REUSE-018).",
                })

            visited_ifs: set[int] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.If) and id(node) not in visited_ifs:
                    cur: Optional[ast.If] = node
                    while cur is not None:
                        visited_ifs.add(id(cur))
                        cur = cur.orelse[0] if len(cur.orelse) == 1 and isinstance(cur.orelse[0], ast.If) else None
                    arms = _if_chain_length(node)
                    if arms >= max_branch_arms:
                        hotspots.append({
                            "code": "REUSE-015-BRANCH-CHAIN",
                            "path": rel,
                            "line": getattr(node, "lineno", 1),
                            "metric": arms,
                            "limit": max_branch_arms - 1,
                            "remediation": "Replace wide if/elif chain with declarative DecisionEngine or CommandSpec table (REUSE-012, REUSE-016).",
                        })

    return {
        "schema": "wellmanifest.horizontal-complexity-report/v1",
        "project": str(root),
        "scanned_files": scanned_files,
        "hotspot_count": len(hotspots),
        "hotspots": hotspots,
    }
