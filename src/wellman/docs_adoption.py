"""Pinned ``wellmanifest/docs`` adoption metadata and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from wellman.repository import RepositoryIdentityError, canonical_repository


# These values are copied from the published wellmanifest/docs policy and are
# deliberately immutable in a wellman release.  Updating the policy requires
# a new wellman release and a new adoption revision.
DOCS_STANDARD_REVISION = "19efafbeb18923cfd51cc69bd519330488500137"
DOCS_POLICY_SHA256 = "fac05e720ec49370ba393e817a4a03b895d7ed33828e09b3420f9fcfb09264b0"
DOCS_ADOPTION_SCHEMA = "wellmanifest.docs/adoption/v1"
DOCS_STANDARD_ID = "wellmanifest/docs"


def expected_adoption(root: Path, repository: Optional[str] = None) -> Dict[str, str]:
    """Build the exact docs adoption record for a repository."""

    return {
        "schema": DOCS_ADOPTION_SCHEMA,
        "repository": canonical_repository(root, repository),
        "standard": DOCS_STANDARD_ID,
        "source_revision": DOCS_STANDARD_REVISION,
        "policy_sha256": DOCS_POLICY_SHA256,
    }


def validate_adoption(
    root: Path, *, required: bool = False, repository: Optional[str] = None
) -> List[Dict[str, str]]:
    """Validate repository-bound docs adoption without writing anything."""

    path = root / ".governance" / "docs.json"
    if not path.exists():
        if required:
            return [
                {
                    "code": "GOV-DOCS-MISSING",
                    "message": "Missing .governance/docs.json",
                    "remediation": "Run `wellman adopt baseline` or adopt wellmanifest/docs explicitly.",
                }
            ]
        return []
    if path.is_symlink():
        return [
            {
                "code": "GOV-DOCS-SYMLINK",
                "message": ".governance/docs.json must not be a symlink",
                "remediation": "Replace it with a repository-local generated adoption record.",
            }
        ]

    try:
        actual: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [
            {
                "code": "GOV-DOCS-JSON",
                "message": f"Malformed .governance/docs.json: {exc}",
                "remediation": "Regenerate the docs adoption record.",
            }
        ]

    try:
        expected = expected_adoption(root, repository)
    except RepositoryIdentityError as exc:
        return [
            {
                "code": "GOV-DOCS-IDENTITY",
                "message": str(exc),
                "remediation": "Configure origin or pass a validated repository identity during adoption.",
            }
        ]

    if actual != expected:
        return [
            {
                "code": "GOV-DOCS-DRIFT",
                "message": "Documentation adoption is not bound to this repository and pinned docs policy.",
                "remediation": "Regenerate .governance/docs.json; never copy it from another repository.",
            }
        ]
    return []


def render_adoption(root: Path, repository: Optional[str] = None) -> str:
    """Render a stable, newline-terminated docs adoption record."""

    return json.dumps(expected_adoption(root, repository), indent=2) + "\n"
