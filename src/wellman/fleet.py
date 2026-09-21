"""Safe discovery, planning and adoption across a directory of repositories."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from wellman import __version__
from wellman.docs_adoption import render_adoption, validate_adoption
from wellman.registry import get_profile, get_standard
from wellman.repository import RepositoryIdentityError, canonical_repository
from wellman.runner import ConformanceRunner
from wellman.validator import Finding


PLAN_SCHEMA = "wellman.fleet-plan/v1"
REPORT_SCHEMA = "wellman.fleet-report/v1"


@dataclass
class RepositoryRecord:
    path: Path
    repository: Optional[str]
    identity_error: Optional[str]
    dirty: bool
    manifest: Optional[Dict[str, Any]]
    manifest_error: Optional[str]


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True, check=False
    )


def is_repository(path: Path) -> bool:
    return path.is_dir() and (path / ".git").exists()


def discover_repositories(root: Path, recursive: bool = False) -> List[Path]:
    """Discover direct child repositories, optionally walking descendants."""

    root = root.resolve()
    if is_repository(root):
        return [root]
    if not root.is_dir():
        return []

    if not recursive:
        return sorted(
            (
                child
                for child in root.iterdir()
                if not child.name.startswith(".") and is_repository(child)
            ),
            key=lambda item: item.as_posix(),
        )

    found: List[Path] = []
    for current, directories, _files in os.walk(root):
        current_path = Path(current)
        if current_path != root and is_repository(current_path):
            found.append(current_path)
            directories[:] = []
            continue
        directories[:] = [
            name
            for name in directories
            if name not in {".git", ".subactor", "node_modules"}
            and not name.startswith(".")
        ]
    return sorted(found, key=lambda item: item.as_posix())


def _is_dirty(path: Path) -> bool:
    result = _git(path, "status", "--porcelain", "--untracked-files=all")
    return result.returncode != 0 or bool(result.stdout.strip())


def inspect_repository(path: Path) -> RepositoryRecord:
    manifest_path = path / ".governance" / "manifest.json"
    manifest: Optional[Dict[str, Any]] = None
    manifest_error: Optional[str] = None
    if manifest_path.exists():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("manifest must be a JSON object")
            manifest = loaded
        except (OSError, ValueError) as exc:
            manifest_error = str(exc)

    try:
        repository = canonical_repository(path)
        identity_error = None
    except RepositoryIdentityError as exc:
        repository = None
        identity_error = str(exc)

    return RepositoryRecord(
        path=path,
        repository=repository,
        identity_error=identity_error,
        dirty=_is_dirty(path),
        manifest=manifest,
        manifest_error=manifest_error,
    )


def _profile_contains(profile_name: str, target: str, seen: Optional[set] = None) -> bool:
    seen = set() if seen is None else seen
    if profile_name in seen:
        return False
    seen.add(profile_name)
    profile = get_profile(profile_name)
    if profile is None:
        return False
    if any(item.get("id") == target for item in profile.requirements):
        return True
    return any(_profile_contains(parent, target, seen) for parent in profile.extends)


def target_is_valid(target: str) -> bool:
    return get_standard(target) is not None or get_profile(target) is not None


def target_requires_docs(target: str) -> bool:
    standard = get_standard(target)
    if standard is not None:
        return standard.id == "wellmanifest/docs"
    return _profile_contains(target, "wellmanifest/docs")


def _manifest_header_requires_update(manifest: Dict[str, Any]) -> bool:
    standard = manifest.get("standard")
    if not isinstance(standard, dict):
        return False
    standard_id = standard.get("id")
    return standard_id == "wellmanifest/new-project" or (
        isinstance(standard_id, str) and standard_id.startswith("profile:")
    )


def _manifest_with_updated_headers(manifest: Dict[str, Any]) -> Dict[str, Any]:
    updated = json.loads(json.dumps(manifest))
    standard = updated.get("standard")
    if isinstance(standard, dict) and (
        standard.get("id") == "wellmanifest/new-project"
        or str(standard.get("id", "")).startswith("profile:")
    ):
        standard["version"] = __version__
    for item in updated.get("standards", []):
        if isinstance(item, dict) and item.get("id") in {
            "wellmanifest/new-project",
            "wellmanifest/wellman",
        }:
            item["version"] = __version__
    return updated


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.wellman.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _plan_record(record: RepositoryRecord, target: str, allow_dirty: bool, update_manifests: bool) -> Dict[str, Any]:
    actions: List[str] = []
    blockers: List[str] = []
    if record.identity_error:
        blockers.append(record.identity_error)
    if record.manifest_error:
        blockers.append(f"invalid manifest: {record.manifest_error}")
    if record.dirty and not allow_dirty:
        blockers.append("working tree is dirty")
    if record.manifest is None:
        actions.append("create .governance/manifest.json")
    elif update_manifests and _manifest_header_requires_update(record.manifest):
        actions.append("update managed manifest version headers")
    elif update_manifests:
        blockers.append("manifest has no wellman-owned version header")
    if target_requires_docs(target):
        docs_findings = validate_adoption(record.path, required=True, repository=record.repository)
        if docs_findings:
            actions.append("write .governance/docs.json")
            if (record.path / ".governance" / "manifest.lock.json").is_file():
                actions.append("refresh docs.json digest in manifest.lock.json")
    return {
        "path": str(record.path),
        "repository": record.repository,
        "dirty": record.dirty,
        "actions": actions,
        "blockers": blockers,
        "ready": not blockers,
    }


def build_plan(root: Path, target: str, recursive: bool = False, allow_dirty: bool = False, update_manifests: bool = False) -> Dict[str, Any]:
    if not target_is_valid(target):
        raise ValueError(f"unknown standard or profile: {target}")
    records = [inspect_repository(path) for path in discover_repositories(root, recursive)]
    repositories = [_plan_record(record, target, allow_dirty, update_manifests) for record in records]
    return {
        "schema": PLAN_SCHEMA,
        "root": str(root.resolve()),
        "target": target,
        "repositories": repositories,
        "ready": sum(1 for item in repositories if item["ready"]),
        "blocked": sum(1 for item in repositories if not item["ready"]),
    }


def apply_plan(plan: Dict[str, Any], target: str, update_manifests: bool = False) -> Dict[str, Any]:
    """Apply only the actions present in a previously built plan."""

    results: List[Dict[str, Any]] = []
    for item in plan["repositories"]:
        result = dict(item)
        if not item["ready"]:
            result["status"] = "skipped"
            results.append(result)
            continue
        path = Path(item["path"])
        gov_dir = path / ".governance"
        gov_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = gov_dir / "manifest.json"
        manifest = None
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest is None:
            manifest = {
                "schema": "wellmanifest.manifest/v1",
                "standard": {"id": f"profile:{target}" if get_profile(target) else get_standard(target).id, "version": __version__},
            }
            _atomic_write(manifest_path, _json_bytes(manifest))
        elif update_manifests and _manifest_header_requires_update(manifest):
            _atomic_write(manifest_path, _json_bytes(_manifest_with_updated_headers(manifest)))

        packs = Path(__file__).parent / "schemas" / "standard-packs.json"
        target_packs = gov_dir / "standard-packs.json"
        if packs.is_file() and not target_packs.exists():
            _atomic_write(target_packs, packs.read_bytes())

        if target_requires_docs(target):
            docs_path = gov_dir / "docs.json"
            docs_content = render_adoption(path, item["repository"])
            _atomic_write(docs_path, docs_content.encode("utf-8"))
            lock_path = gov_dir / "manifest.lock.json"
            if lock_path.is_file():
                lock = json.loads(lock_path.read_text(encoding="utf-8"))
                managed = lock.get("managedFiles")
                if isinstance(managed, dict):
                    managed[".governance/docs.json"] = hashlib.sha256(docs_content.encode("utf-8")).hexdigest()
                    _atomic_write(lock_path, _json_bytes(lock))
        result["status"] = "updated"
        results.append(result)
    return {"schema": REPORT_SCHEMA, "target": target, "repositories": results}


def check_fleet(root: Path, recursive: bool = False) -> Dict[str, Any]:
    repositories: List[Dict[str, Any]] = []
    for path in discover_repositories(root, recursive):
        record = inspect_repository(path)
        findings = ConformanceRunner(path).run_all()
        if record.identity_error:
            findings.append(
                Finding(
                    code="GOV-REPOSITORY-IDENTITY",
                    message=record.identity_error,
                    severity="ERROR",
                    remediation="Configure origin or exclude the checkout from the fleet.",
                )
            )
        repositories.append({
            "path": str(path),
            "repository": record.repository,
            "valid": not any(item.severity == "ERROR" for item in findings),
            "findings": [item.to_dict() for item in findings],
        })
    return {
        "schema": REPORT_SCHEMA,
        "root": str(root.resolve()),
        "repositories": repositories,
        "valid": all(item["valid"] for item in repositories),
    }
