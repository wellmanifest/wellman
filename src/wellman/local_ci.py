"""Local OneDev + Validator publication scope (new-project.local-ci-publication/v1).

The local route is the default for every repository.  An adopter may only
narrow it with `.governance/local-ci-publication.json`; a restriction never
grants, widens or removes publication authority.  An absent or malformed file
leaves the unrestricted default in force.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = "new-project.local-ci-publication/v1"
POLICY_PATH = Path(".governance") / "local-ci-publication.json"
DEFAULT_POLICY: Dict[str, Any] = {"schema": SCHEMA, "scope": {"mode": "all"}}
_REPOSITORY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/(\*|[A-Za-z0-9._-]+)$")


def validate_policy(document: Any) -> List[str]:
    """Return schema violations; an empty list means the document is valid."""
    if not isinstance(document, dict):
        return ["policy must be a JSON object"]
    errors: List[str] = []
    if set(document) - {"schema", "scope"}:
        errors.append(f"unknown fields: {sorted(set(document) - {'schema', 'scope'})}")
    if document.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    scope = document.get("scope")
    if not isinstance(scope, dict):
        return errors + ["scope must be an object"]
    if set(scope) - {"mode", "repositories"}:
        errors.append(f"unknown scope fields: {sorted(set(scope) - {'mode', 'repositories'})}")
    mode = scope.get("mode")
    repositories = scope.get("repositories")
    if mode == "all":
        if "repositories" in scope:
            errors.append("mode all must not list repositories")
    elif mode == "restricted":
        if (not isinstance(repositories, list) or not repositories
                or len(set(map(str, repositories))) != len(repositories)
                or not all(isinstance(item, str) and _REPOSITORY.match(item) for item in repositories)):
            errors.append("mode restricted requires a non-empty unique list of OWNER/REPO or OWNER/* entries")
    else:
        errors.append("scope.mode must be all or restricted")
    return errors


def read_policy(root: Path) -> Tuple[Dict[str, Any], Optional[str]]:
    """Return the effective policy and a problem description, if any.

    Absent file: unrestricted default, no problem.  Malformed file: the
    unrestricted default applies and the problem is reported.
    """
    path = Path(root) / POLICY_PATH
    if path.is_symlink():
        return dict(DEFAULT_POLICY), f"refusing symlink: {POLICY_PATH}"
    if not path.exists():
        return dict(DEFAULT_POLICY), None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return dict(DEFAULT_POLICY), f"unreadable policy: {error}"
    errors = validate_policy(document)
    if errors:
        return dict(DEFAULT_POLICY), "; ".join(errors)
    return document, None


def applies_to(policy: Dict[str, Any], repository: str) -> bool:
    """True when the local route is the default for OWNER/REPO."""
    scope = policy.get("scope", {})
    if scope.get("mode") != "restricted":
        return True
    owner = repository.split("/", 1)[0]
    return any(item == repository or item == f"{owner}/*" for item in scope.get("repositories", []))


def ensure_default_policy(root: Path, *, dry_run: bool = False) -> Dict[str, Any]:
    """Write the unrestricted default when absent; never replace an existing file."""
    root = Path(root)
    governance = root / ".governance"
    path = root / POLICY_PATH
    if governance.is_symlink() or path.is_symlink():
        raise ValueError(f"Refusing symlink: {path}")
    if path.exists():
        policy, problem = read_policy(root)
        return {"changed": False, "path": str(path), "policy": policy, "problem": problem}
    if not dry_run:
        governance.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=governance,
                                         prefix=".local-ci-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(DEFAULT_POLICY, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            # os.link fails if another writer created the file meanwhile.
            os.link(temporary, path)
        except FileExistsError:
            policy, problem = read_policy(root)
            return {"changed": False, "path": str(path), "policy": policy, "problem": problem}
        finally:
            temporary.unlink()
    return {"changed": True, "dry_run": dry_run, "path": str(path),
            "policy": dict(DEFAULT_POLICY), "problem": None}
