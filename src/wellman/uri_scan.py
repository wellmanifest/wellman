"""URI link scanning confined to the explicitly selected source tree."""
from pathlib import Path
from typing import Any, Dict, List
import os
import re


def _source_paths(root, ignored, extensions):
    for directory, children, names in os.walk(root, followlinks=False):
        children[:] = sorted(name for name in children if name not in ignored
                             and not (Path(directory) / name).is_symlink())
        for name in names:
            path = Path(directory) / name
            if path.suffix in extensions and not path.is_symlink() and path.is_file():
                yield path


# Regexes for polyglot `uri('...')` link verification and duplication scanning
_POLYGLOT_URI_CALL_RE = re.compile(
    r"""(?:\buri\s*\(\s*['"]([^'"]+)['"]|\buri\s+['"]([a-z][a-z0-9+.-]*://[^'"]+)['"])"""
)
_SUBPROCESS_DUP_RE = re.compile(
    r"""(?:subprocess\.(?:run|check_output|Popen)\s*\(\s*\[[^\]]*(?:policy_dsl_check|lifecycle\.py|dockuri|curictl|urirun))"""
)


def scan_links(root: Path, validate, invocation_error) -> Dict[str, Any]:
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

    for path in sorted(_source_paths(root, ignored, extensions)):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        rel = str(path.relative_to(root))
        for line_no, line in enumerate(text.splitlines(), start=1):
            for match in _POLYGLOT_URI_CALL_RE.finditer(line):
                raw_uri = match.group(1) or match.group(2) or ""
                try:
                    validate(raw_uri)
                    valid_links.append({"path": rel, "line": line_no, "uri": raw_uri})
                except invocation_error as exc:
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

