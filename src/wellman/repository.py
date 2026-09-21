"""Repository identity helpers used by adoption and conformance checks."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional


REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class RepositoryIdentityError(ValueError):
    """Raised when a repository cannot be bound to a canonical identity."""


def _normalize_remote(value: str) -> Optional[str]:
    value = value.strip()
    patterns = (
        r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([\w.-]+/[\w.-]+?)(?:\.git)?$",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, value, re.IGNORECASE)
        if match and REPOSITORY.fullmatch(match.group(1)):
            return match.group(1)
    return None


def canonical_repository(root: Path, explicit: Optional[str] = None) -> str:
    """Return the GitHub ``owner/repository`` identity for *root*.

    Adoption metadata is repository-bound.  A missing or malformed ``origin``
    is therefore an error instead of a reason to invent a placeholder value.
    ``explicit`` is available for repositories whose remote is intentionally
    unavailable during bootstrap, but is still validated against the same
    canonical format.
    """

    if explicit is not None:
        if not REPOSITORY.fullmatch(explicit.strip()):
            raise RepositoryIdentityError(
                "--repository must contain a canonical GitHub owner/name"
            )
        return explicit.strip()

    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RepositoryIdentityError(
            "Git remote 'origin' is required for repository-bound adoption; "
            "use --repository owner/name when the remote is intentionally unavailable"
        )
    repository = _normalize_remote(result.stdout)
    if repository is None:
        raise RepositoryIdentityError(
            "Git remote 'origin' must be a supported GitHub URL"
        )
    return repository
