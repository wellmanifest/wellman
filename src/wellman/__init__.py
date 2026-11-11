"""Wellman — Wellmanifest Unified Standards Runtime.

Deterministic policy-as-code checker, standard registry, and validator
for all Wellmanifest standards.
"""

from __future__ import annotations

from importlib.metadata import version as _get_version
from pathlib import Path as _Path


def _resolve_version() -> str:
    checkout_root = _Path(__file__).resolve().parents[2]
    version_file = checkout_root / "VERSION"
    if (checkout_root / "pyproject.toml").is_file() and version_file.is_file():
        version_text = version_file.read_text(encoding="utf-8").strip()
        if version_text:
            return version_text
    try:
        return _get_version("wellman")
    except Exception:
        return "0.23.0"


__version__ = _resolve_version()

from wellman.registry import (
    CONFORMANCE_LEVELS,
    EXECUTION_MODELS,
    PROFILES_CATALOG,
    STANDARDS_CATALOG,
    Profile,
    StandardPack,
    get_profile,
    get_standard,
    list_profiles,
    list_standards,
)
from wellman.runner import ConformanceRunner
from wellman.uri import register_uri_process, uri
from wellman.validator import Finding, StandardsValidator

__all__ = [
    "__version__",
    "StandardPack",
    "Profile",
    "STANDARDS_CATALOG",
    "PROFILES_CATALOG",
    "CONFORMANCE_LEVELS",
    "EXECUTION_MODELS",
    "get_standard",
    "list_standards",
    "get_profile",
    "list_profiles",
    "StandardsValidator",
    "ConformanceRunner",
    "Finding",
    "uri",
    "register_uri_process",
]
