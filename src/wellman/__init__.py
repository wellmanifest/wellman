"""Wellman — Wellmanifest Unified Standards Runtime.

Deterministic policy-as-code checker, standard registry, and validator
for all Wellmanifest standards.
"""

from __future__ import annotations

from importlib.metadata import version as _get_version

try:
    __version__ = _get_version("wellman")
except Exception:
    __version__ = "0.20.32"

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
]
