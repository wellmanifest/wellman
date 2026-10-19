"""Universal URI Process Invocation Library and CLI (`uri`).

Provides a single deterministic invocation contract across languages and scripts:
- Python library function: `from wellman.uri import uri`
    `uri("proc://ast-scan/complexity/horizontal", {"root": "."})`
    `uri("proc://policy-dsl/audit", {"source": "..."})`
- Shell / polyglot CLI command: `uri`
    `uri 'proc://ast-scan/complexity/horizontal' '{"root":"."}'`
    `uri 'proc://ast-scan/complexity/horizontal' < requests.jsonl`
    `uri --jsonl < dockuri-batch.jsonl`

Routes invocations through a prioritized DependencyResolver chain:
1. `floor:in_process_registry` (zero-subprocess native/Rust FFI & bundled handlers)
2. `standard:dockuri_router` (`uri_process_router` / `dockuri` Python runtime)
3. `standard:dockuri_cli_jsonl` (`dockuri sh` stdin/stdout JSONL protocol)
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union
from urllib.parse import urlsplit

from wellman.stream_flow import (
    DependencyResolver,
    PrioritizedDependency,
    StreamEnvelope,
    StreamPipeline,
    StreamStage,
    analyze_horizontal_complexity,
)

INVOCATION_SCHEMA = "uriprocess.invocation/v1"
RESULT_SCHEMA = "uriprocess.invocation-result/v1"

_URI_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*://[^\s/?#]+/[^\s?#]*$")

# Global in-process registry of URI process handlers
_PROCESS_REGISTRY: Dict[str, Callable[[Dict[str, Any]], Any]] = {}


class UriInvocationError(ValueError):
    """Raised when a URI process invocation is malformed or cannot be dispatched."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.detail = message


def validate_process_uri(address: str) -> str:
    """Validate a canonical URI process address (`scheme://authority/path`)."""
    if not isinstance(address, str) or not address.strip():
        raise UriInvocationError("URP-IDENTITY-001", "URI address must be a non-empty string")
    address = address.strip()
    if not _URI_PATTERN.match(address):
        raise UriInvocationError(
            "URP-IDENTITY-001",
            f"Invalid process URI '{address}': expected 'scheme://authority/path' without query or fragment",
        )
    parsed = urlsplit(address)
    if (
        not parsed.scheme
        or not parsed.hostname
        or not parsed.path
        or parsed.path == "/"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise UriInvocationError(
            "URP-IDENTITY-001",
            f"Invalid process URI '{address}': credentials, queries, and fragments are forbidden",
        )
    return address


def register_uri_process(address: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
    """Register an in-process handler for a canonical URI process."""
    canonical = validate_process_uri(address)
    _PROCESS_REGISTRY[canonical] = handler


def list_registered_uri_processes() -> List[str]:
    """Return sorted list of registered in-process URI addresses."""
    _ensure_builtin_processes()
    return sorted(_PROCESS_REGISTRY.keys())


def _load_bundled_module(script_name: str, mod_name: str) -> Any:
    existing = sys.modules.get(mod_name)
    if existing is not None:
        return existing
    script_path = Path(__file__).parent / "_bundled" / script_name
    if not script_path.is_file():
        raise UriInvocationError("URP-RUNTIME-001", f"Bundled module '{script_name}' not found")
    spec = importlib.util.spec_from_file_location(mod_name, script_path)
    if spec is None or spec.loader is None:
        raise UriInvocationError("URP-RUNTIME-001", f"Cannot load bundled module '{script_name}'")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _handle_ast_horizontal(args: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(str(args.get("root", ".")))
    max_branches = int(args.get("max_branches", 5))
    max_fan_out = int(args.get("max_fan_out", 12))
    max_file_lines = int(args.get("max_file_lines", 500))
    return analyze_horizontal_complexity(
        root,
        max_branch_arms=max_branches,
        max_fan_out=max_fan_out,
        max_file_lines=max_file_lines,
    )


def _handle_policy_dsl_validate(args: Dict[str, Any]) -> Dict[str, Any]:
    mod = _load_bundled_module("policy_dsl_check.py", "_wellman_uri_policy_dsl")
    if "path" in args:
        source = Path(str(args["path"])).read_text(encoding="utf-8")
        markdown = str(args["path"]).endswith(".md") or bool(args.get("markdown", False))
    else:
        source = str(args.get("source", ""))
        markdown = bool(args.get("markdown", False))
    ir = mod.parse_markdown(source) if markdown else mod.parse(source)
    return {
        "valid": True,
        "document": ir.get("document"),
        "version": ir.get("version"),
        "rules": len(ir.get("rules", [])),
        "states": len(ir.get("states", [])),
        "transitions": len(ir.get("transitions", [])),
    }


def _handle_policy_dsl_audit(args: Dict[str, Any]) -> Dict[str, Any]:
    mod = _load_bundled_module("policy_dsl_check.py", "_wellman_uri_policy_dsl")
    if "path" in args:
        source = Path(str(args["path"])).read_text(encoding="utf-8")
        markdown = str(args["path"]).endswith(".md") or bool(args.get("markdown", False))
    else:
        source = str(args.get("source", ""))
        markdown = bool(args.get("markdown", False))
    return mod.audit_compaction(source, markdown=markdown)


def _handle_lifecycle_dsl_validate(args: Dict[str, Any]) -> Dict[str, Any]:
    mod = _load_bundled_module("lifecycle.py", "_wellman_uri_lifecycle_dsl")
    catalog = mod.embedded_catalog()
    if "path" in args:
        report = mod.validate_path(Path(str(args["path"])), catalog)
    else:
        source = str(args.get("source", ""))
        report = mod.validate_text(source, source="<memory>", catalog=catalog)
    if not report.valid:
        diag_msgs = "; ".join(f"{d.code}: {d.message} ({d.detail})" for d in report.diagnostics)
        raise UriInvocationError("LFC-VALIDATION-FAILED", diag_msgs or "Invalid lifecycle bundle")
    return report.as_dict()


def _handle_lifecycle_dsl_audit(args: Dict[str, Any]) -> Dict[str, Any]:
    mod = _load_bundled_module("lifecycle.py", "_wellman_uri_lifecycle_dsl")
    if "path" in args:
        return mod.audit_path(Path(str(args["path"])))
    source = str(args.get("source", ""))
    return mod.audit_compaction(source)


def _handle_scan_uri_links(args: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(str(args.get("root", ".")))
    return scan_uri_link_opportunities(root)


def _ensure_builtin_processes() -> None:
    if _PROCESS_REGISTRY:
        return
    builtins: Dict[str, Callable[[Dict[str, Any]], Any]] = {
        "proc://ast-scan/complexity/horizontal": _handle_ast_horizontal,
        "willman://operation/ast-horizontal-complexity/v1": _handle_ast_horizontal,
        "proc://policy-dsl/validate": _handle_policy_dsl_validate,
        "proc://policy-dsl/audit": _handle_policy_dsl_audit,
        "proc://lifecycle-dsl/validate": _handle_lifecycle_dsl_validate,
        "proc://lifecycle-dsl/audit": _handle_lifecycle_dsl_audit,
        "proc://uriprocess/invocation/scan": _handle_scan_uri_links,
    }
    for addr, fn in builtins.items():
        _PROCESS_REGISTRY[addr] = fn


def _normalize_jsonl_items(
    address: Optional[str],
    payload: Any,
) -> List[Dict[str, Any]]:
    """Normalize single payload, JSON string, JSONL string, or list into canonical request envelopes."""
    items: List[Dict[str, Any]] = []

    def _wrap_one(idx: int, obj: Any, default_uri: Optional[str]) -> Dict[str, Any]:
        if not isinstance(obj, dict):
            raise UriInvocationError("URP-DATA-001", f"Payload at index {idx} must be a JSON object")
        if "uri" in obj and ("args" in obj or "payload" in obj):
            req_uri = validate_process_uri(str(obj["uri"]))
            req_args = obj.get("args") if "args" in obj else obj.get("payload", {})
            if not isinstance(req_args, dict):
                raise UriInvocationError("URP-DATA-001", f"'args' at index {idx} must be a JSON object")
            req_id = str(obj.get("id", f"r{idx + 1}"))
            return {"schema": INVOCATION_SCHEMA, "id": req_id, "uri": req_uri, "args": req_args}
        if not default_uri:
            raise UriInvocationError("URP-IDENTITY-001", f"Missing 'uri' in JSONL object at index {idx}")
        req_uri = validate_process_uri(default_uri)
        req_id = str(obj.get("_id", f"r{idx + 1}"))
        clean_args = {k: v for k, v in obj.items() if k != "_id"}
        return {"schema": INVOCATION_SCHEMA, "id": req_id, "uri": req_uri, "args": clean_args}

    if payload is None:
        if not address:
            raise UriInvocationError("URP-IDENTITY-001", "URI address is required when payload is empty")
        return [{"schema": INVOCATION_SCHEMA, "id": "r1", "uri": validate_process_uri(address), "args": {}}]

    if isinstance(payload, dict):
        return [_wrap_one(0, payload, address)]

    if isinstance(payload, str):
        stripped = payload.strip()
        if not stripped:
            if not address:
                raise UriInvocationError("URP-IDENTITY-001", "URI address is required when payload is empty")
            return [{"schema": INVOCATION_SCHEMA, "id": "r1", "uri": validate_process_uri(address), "args": {}}]
        lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
        for idx, line in enumerate(lines):
            try:
                parsed = json.loads(line)
            except ValueError as exc:
                raise UriInvocationError("URP-DATA-001", f"Invalid JSON on line {idx + 1}: {exc}") from exc
            items.append(_wrap_one(idx, parsed, address))
        return items

    if isinstance(payload, Iterable):
        for idx, elem in enumerate(payload):
            if isinstance(elem, str):
                line = elem.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except ValueError as exc:
                    raise UriInvocationError("URP-DATA-001", f"Invalid JSONL item at index {idx}: {exc}") from exc
                items.append(_wrap_one(idx, parsed, address))
            else:
                items.append(_wrap_one(idx, elem, address))
        return items

    raise UriInvocationError("URP-DATA-001", f"Unsupported payload type: {type(payload).__name__}")


def _dispatch_single_request(req: Dict[str, Any], *, timeout: float = 30.0) -> Dict[str, Any]:
    """Dispatch a single canonical URI request through prioritized DependencyResolver tiers."""
    _ensure_builtin_processes()
    target_uri = req["uri"]
    args = req["args"]
    req_id = req["id"]

    def _has_in_process() -> bool:
        return target_uri in _PROCESS_REGISTRY

    def _has_dockuri_router() -> bool:
        if target_uri in _PROCESS_REGISTRY:
            return False
        try:
            import uri_process_router.executor  # noqa: F401
            return True
        except ImportError:
            return False

    def _has_dockuri_cli() -> bool:
        if target_uri in _PROCESS_REGISTRY:
            return False
        return shutil.which("dockuri") is not None

    resolver = DependencyResolver(
        [
            PrioritizedDependency(
                id="in_process_registry",
                capability="uri_dispatch",
                tier="floor",
                weight=100.0,
                provider=lambda: ("in_process_registry", _PROCESS_REGISTRY[target_uri](args)),
                readiness_probe=_has_in_process,
                fallback_id="dockuri_router",
            ),
            PrioritizedDependency(
                id="dockuri_router",
                capability="uri_dispatch",
                tier="standard",
                weight=80.0,
                provider=lambda: _invoke_dockuri_router(target_uri, args),
                readiness_probe=_has_dockuri_router,
                fallback_id="dockuri_cli_jsonl",
            ),
            PrioritizedDependency(
                id="dockuri_cli_jsonl",
                capability="uri_dispatch",
                tier="standard",
                weight=60.0,
                provider=lambda: _invoke_dockuri_cli_jsonl(req_id, target_uri, args, timeout=timeout),
                readiness_probe=_has_dockuri_cli,
            ),
        ]
    )

    req_canonical = json.dumps({"id": req_id, "uri": target_uri, "args": args}, sort_keys=True)
    req_sha = hashlib.sha256(req_canonical.encode("utf-8")).hexdigest()

    try:
        resolved = resolver.resolve("uri_dispatch")
        provider_name, raw_result = resolved.value
        tier = resolved.tier
        ok = True
    except Exception as exc:
        raise UriInvocationError(
            "URP-DISPATCH-001",
            f"No ready URI process provider for '{target_uri}': {exc}",
        ) from exc

    res_canonical = json.dumps(raw_result, sort_keys=True, default=str)
    res_sha = hashlib.sha256(f"{req_sha}:{res_canonical}".encode("utf-8")).hexdigest()

    return {
        "schema": RESULT_SCHEMA,
        "id": req_id,
        "uri": target_uri,
        "ok": ok,
        "tier": tier,
        "provider": provider_name,
        "result": raw_result,
        "receipt": {
            "request_sha256": req_sha,
            "sha256": res_sha,
        },
    }


def _invoke_dockuri_router(target_uri: str, args: Dict[str, Any]) -> Tuple[str, Any]:
    from uri_process_router.executor import ProcessExecutor  # type: ignore

    executor = ProcessExecutor()
    out = executor.execute({"status": "ok", "uri": target_uri, "arguments": args})
    return "dockuri_router", out


def _invoke_dockuri_cli_jsonl(
    req_id: str,
    target_uri: str,
    args: Dict[str, Any],
    *,
    timeout: float = 30.0,
) -> Tuple[str, Any]:
    line = json.dumps({"id": req_id, "uri": target_uri, "args": args}) + "\n"
    proc = subprocess.run(
        ["dockuri", "sh", "--allow-native", "--allow-effects", "pure,read"],
        input=line,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=tempfile.gettempdir(),
        check=False,
    )
    if proc.returncode != 0:
        raise UriInvocationError("URP-DISPATCH-002", proc.stderr.strip() or f"dockuri sh exited {proc.returncode}")
    for out_line in reversed([ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]):
        try:
            return "dockuri_cli_jsonl", json.loads(out_line)
        except ValueError:
            continue
    return "dockuri_cli_jsonl", {"stdout": proc.stdout.strip()}


def uri(
    address: str = "",
    payload: Any = None,
    *,
    stream: bool = False,
    timeout: float = 30.0,
) -> Any:
    """Invoke a Dockuri / Wellmanifest URI process by full URI address and JSON/JSONL payload.

    Examples:
        # Single call in Python
        res = uri("proc://ast-scan/complexity/horizontal", {"root": "."})

        # Multi-item JSONL stream through StreamPipeline
        results = uri(
            "proc://policy-dsl/audit",
            '{"source": "..."}\\n{"source": "..."}',
            stream=True,
        )
    """
    requests = _normalize_jsonl_items(address if address else None, payload)
    pipeline = StreamPipeline(
        "uri_invocation_pipeline",
        [
            StreamStage(
                id="dispatch_uri",
                kind="module",
                tier="floor",
                weight=100.0,
                transform=lambda env: _dispatch_single_request(env.payload, timeout=timeout),
            )
        ],
    )
    envelopes: List[StreamEnvelope[Dict[str, Any]]] = list(pipeline.stream(requests))
    results = [env.payload for env in envelopes]
    if stream or len(results) != 1 or (isinstance(payload, list)):
        return results
    return results[0]


# Regexes for polyglot `uri('...')` link verification and duplication scanning
_POLYGLOT_URI_CALL_RE = re.compile(
    r"""(?:\buri\s*\(\s*['"]([^'"]+)['"]|\buri\s+['"]([a-z][a-z0-9+.-]*://[^'"]+)['"])"""
)
_SUBPROCESS_DUP_RE = re.compile(
    r"""(?:subprocess\.(?:run|check_output|Popen)\s*\(\s*\[[^\]]*(?:policy_dsl_check|lifecycle\.py|dockuri|curictl|urirun))"""
)


def scan_uri_link_opportunities(root: Path) -> Dict[str, Any]:
    """Scan scripts across languages for `uri(...)` links and subprocess calls replaceable by `uri(...)`."""
    root = root.resolve()
    valid_links: List[Dict[str, Any]] = []
    invalid_links: List[Dict[str, Any]] = []
    migration_candidates: List[Dict[str, Any]] = []

    ignored = {
        ".git", ".worktrees", ".subactor", ".venv", "venv", "node_modules",
        "target", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        "build", "dist",
    }
    extensions = {".py", ".sh", ".mjs", ".js", ".ts", ".rs", ".policy", ".curi"}

    for path in sorted(root.rglob("*")):
        if any(part in ignored for part in path.parts):
            continue
        if not path.is_file() or path.suffix not in extensions:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        rel = str(path.relative_to(root))
        for line_no, line in enumerate(text.splitlines(), start=1):
            for match in _POLYGLOT_URI_CALL_RE.finditer(line):
                raw_uri = match.group(1) or match.group(2) or ""
                try:
                    validate_process_uri(raw_uri)
                    valid_links.append({"path": rel, "line": line_no, "uri": raw_uri})
                except UriInvocationError as exc:
                    invalid_links.append({
                        "code": exc.code,
                        "path": rel,
                        "line": line_no,
                        "uri": raw_uri,
                        "message": exc.detail,
                    })
            if path.name != "uri.py" and _SUBPROCESS_DUP_RE.search(line):
                migration_candidates.append({
                    "code": "URP-LINK-CANDIDATE",
                    "path": rel,
                    "line": line_no,
                    "message": "Direct subprocess invocation of URI/DSL tool can be replaced with canonical `uri('<scheme>://<authority>/<path>', payload)`.",
                })

    return {
        "schema": "uriprocess.link-scan/v1",
        "root": str(root),
        "valid_link_count": len(valid_links),
        "invalid_link_count": len(invalid_links),
        "migration_candidate_count": len(migration_candidates),
        "valid_links": valid_links,
        "invalid_links": invalid_links,
        "migration_candidates": migration_candidates,
    }


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint for `uri <full-uri> [json-or-jsonl]`."""
    parser = argparse.ArgumentParser(
        prog="uri",
        description="Invoke a Dockuri / Wellmanifest URI process with JSON or JSONL payload.",
    )
    parser.add_argument("address", nargs="?", default="", help="Full process URI (e.g. proc://ast-scan/complexity/horizontal)")
    parser.add_argument("payload", nargs="?", default=None, help="Inline JSON object or JSONL string (reads stdin if omitted and piped)")
    parser.add_argument("--jsonl", action="store_true", help="Stream JSONL input/output lines")
    parser.add_argument("--list", action="store_true", help="List registered in-process URI routes")
    parser.add_argument("--scan", metavar="PATH", help="Scan a directory for polyglot uri('') links and migration candidates")
    parser.add_argument("--timeout", type=float, default=30.0, help="Execution timeout in seconds")
    args = parser.parse_args(argv)

    if args.list:
        print(json.dumps({"schema": "uriprocess.routes/v1", "routes": list_registered_uri_processes()}, indent=2))
        return 0

    if args.scan:
        report = scan_uri_link_opportunities(Path(args.scan))
        print(json.dumps(report, indent=2))
        return 1 if report["invalid_link_count"] > 0 else 0

    raw_payload: Any = args.payload
    if raw_payload is None and not sys.stdin.isatty():
        raw_payload = sys.stdin.read()

    if not args.address and not args.jsonl and not raw_payload:
        parser.print_help(sys.stderr)
        return 2

    try:
        out = uri(args.address, raw_payload, stream=args.jsonl, timeout=args.timeout)
    except UriInvocationError as exc:
        print(json.dumps({"schema": RESULT_SCHEMA, "ok": False, "error": exc.code, "message": exc.detail}), file=sys.stderr)
        return 2

    if isinstance(out, list):
        for item in out:
            print(json.dumps(item, sort_keys=True))
    else:
        print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
