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
from wellman.adoption import register
from wellman.docs_adoption import render_adoption, validate_adoption
from wellman.local_ci import ensure_default_policy
from wellman.registry import get_profile, get_standard
from wellman.repository import RepositoryIdentityError, canonical_repository
from wellman.runner import ConformanceRunner
from wellman.validator import Finding


PLAN_SCHEMA = "wellman.fleet-plan/v1"
REPORT_SCHEMA = "wellman.fleet-report/v1"
AGENT_INSTRUCTION_PATHS = (
    "AGENTS.md", "GEMINI.md", "CLAUDE.md",
    ".cursor/rules/new-project-standard.mdc", ".github/copilot-instructions.md",
    ".aider.conf.yml",
)


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


def discover_repositories(root: Path, recursive: Optional[bool] = None) -> List[Path]:
    """Discover repositories contextually based on directory structure.

    - If *root* is a repository, returns [root].
    - If *recursive* is True, always walks all descendants.
    - If *recursive* is False, strictly checks only direct children.
    - If *recursive* is None (auto mode / default):
      * If direct child repositories exist, returns them.
      * If no direct repositories exist, but subdirectories contain repositories
        (e.g., umbrella or organization folders like ~/github/org/repo),
        automatically discovers them recursively.
    """
    root = root.resolve()
    if is_repository(root):
        return [root]
    if not root.is_dir():
        return []

    direct = sorted(
        (
            child
            for child in root.iterdir()
            if not child.name.startswith(".") and is_repository(child)
        ),
        key=lambda item: item.as_posix(),
    )

    if recursive is False:
        return direct

    if recursive is True or not direct:
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
                if name not in {".git", ".subactor", "node_modules", ".worktrees", "worktrees"}
                and not name.startswith(".")
            ]
        nested = sorted(found, key=lambda item: item.as_posix())
        if recursive is True or not direct:
            return nested

    return direct


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


def _manifest_write_blocker(path: Path, manifest: Optional[Dict[str, Any]], update_manifests: bool) -> Optional[str]:
    """Legacy fleet scaffolding cannot update immutable native adoption pins."""
    lock = path / ".governance" / "manifest.lock.json"
    locked = lock.exists() or lock.is_symlink()
    if manifest is None:
        if locked:
            return "partial locked adoption; restore it through the pinned new-project adopter"
        return None
    schema = manifest.get("schema")
    standard = manifest.get("standard")
    native = locked or (
        isinstance(schema, str) and schema.startswith("new-project.governance/")
    ) or (
        isinstance(standard, dict) and standard.get("id") == "wellmanifest/new-project"
    )
    if native and update_manifests:
        return "native adoption version pins require the pinned new-project adoption/updater"
    return None


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.wellman.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)



def _docs_lock_refreshable(path: Path) -> bool:
    """Only refresh Docs already tracked by a legacy, non-package lock.

    A package map gives its pinned adopter ownership of the entire lock. Fleet
    adoption must not add targets or rewrite that adopter's digest projection.
    """
    gov_dir = path / ".governance"
    package_map = gov_dir / "package-manifest.json"
    if package_map.exists() or package_map.is_symlink():
        return False
    lock_path = gov_dir / "manifest.lock.json"
    if not lock_path.is_file():
        return False
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    managed = lock.get("managedFiles") if isinstance(lock, dict) else None
    return isinstance(managed, dict) and ".governance/docs.json" in managed


def _plan_record(record: RepositoryRecord, target: str, allow_dirty: bool, update_manifests: bool) -> Dict[str, Any]:
    actions: List[str] = []
    blockers: List[str] = []
    if record.identity_error:
        blockers.append(record.identity_error)
    if record.manifest_error:
        blockers.append(f"invalid manifest: {record.manifest_error}")
    if record.dirty and not allow_dirty:
        blockers.append("working tree is dirty")
    governance = record.path / ".governance"
    if governance.is_symlink():
        blockers.append("refusing symlink: .governance")
    else:
        try:
            local_ci = ensure_default_policy(record.path, dry_run=True)
            if local_ci["problem"]:
                blockers.append(f"invalid local CI policy: {local_ci['problem']}")
            elif local_ci["changed"]:
                actions.append("create .governance/local-ci-publication.json")
            registration = register(
                record.path, profiles=[target] if get_profile(target) else [],
                standards=[] if get_profile(target) else [target], dry_run=True,
            )
            requirements = governance / "standard-requirements.json"
            existing = json.loads(requirements.read_text(encoding="utf-8")) if requirements.exists() else None
            if existing != registration["registration"]:
                actions.append("register .governance/standard-requirements.json")
        except (OSError, ValueError) as exc:
            blockers.append(f"unsafe local CI adoption: {exc}")
    packs = Path(__file__).parent / "schemas" / "standard-packs.json"
    target_packs = governance / "standard-packs.json"
    if target_packs.is_symlink():
        blockers.append("refusing symlink: .governance/standard-packs.json")
    elif packs.is_file() and not target_packs.exists():
        actions.append("create .governance/standard-packs.json")
    manifest_blocker = _manifest_write_blocker(record.path, record.manifest, update_manifests)
    if manifest_blocker:
        blockers.append(manifest_blocker)
    if record.manifest is None:
        actions.append("create .governance/manifest.json")
    elif update_manifests and not manifest_blocker and _manifest_header_requires_update(record.manifest):
        actions.append("update managed manifest version headers")
    elif update_manifests and not manifest_blocker:
        blockers.append("manifest has no wellman-owned version header")
    if target_requires_docs(target):
        docs_findings = validate_adoption(record.path, required=True, repository=record.repository)
        if docs_findings:
            actions.append("write .governance/docs.json")
            if _docs_lock_refreshable(record.path):
                actions.append("refresh docs.json digest in manifest.lock.json")
    missing_agents = [f for f in AGENT_INSTRUCTION_PATHS if not (record.path / f).exists()]
    if missing_agents:
        actions.append(f"project agent host instruction contracts ({', '.join(missing_agents)})")
    return {
        "path": str(record.path),
        "repository": record.repository,
        "dirty": record.dirty,
        "actions": actions,
        "blockers": blockers,
        "ready": not blockers,
    }


def build_plan(root: Path, target: str, recursive: Optional[bool] = None, allow_dirty: bool = False, update_manifests: bool = False) -> Dict[str, Any]:
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


def apply_plan(plan: Dict[str, Any], target: str, update_manifests: bool = False, sync_agents: bool = True) -> Dict[str, Any]:
    """Apply only the actions present in a previously built plan."""

    if plan.get("schema") != PLAN_SCHEMA or plan.get("target") != target:
        raise ValueError("fleet plan schema or target does not match requested adoption")
    results: List[Dict[str, Any]] = []
    for item in plan["repositories"]:
        result = dict(item)
        if not item["ready"]:
            result["status"] = "skipped"
            results.append(result)
            continue
        path = Path(item["path"])
        try:
            current = _plan_record(inspect_repository(path), target, bool(item["dirty"]), update_manifests)
        except (OSError, ValueError) as exc:
            current = {"ready": False, "blockers": [f"cannot revalidate fleet plan: {exc}"]}
        if not current["ready"] or any(
            current.get(field) != item.get(field) for field in ("repository", "actions", "dirty")
        ):
            result["blockers"] = [*item["blockers"], *current["blockers"], "fleet plan is stale; rebuild before applying"]
            result["ready"] = False
            result["status"] = "skipped"
            results.append(result)
            continue
        actions = item["actions"]
        if not actions:
            result["status"] = "up-to-date"
            results.append(result)
            continue
        gov_dir = path / ".governance"
        manifest_path = gov_dir / "manifest.json"
        manifest = None
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_blocker = _manifest_write_blocker(path, manifest, update_manifests)
        if manifest_blocker:
            result["blockers"] = [*item["blockers"], manifest_blocker]
            result["ready"] = False
            result["status"] = "skipped"
            results.append(result)
            continue
        gov_dir.mkdir(parents=True, exist_ok=True)
        if "create .governance/manifest.json" in actions:
            manifest = {
                "schema": "wellmanifest.manifest/v1",
                "standard": {"id": f"profile:{target}" if get_profile(target) else get_standard(target).id, "version": __version__},
            }
            _atomic_write(manifest_path, _json_bytes(manifest))
        elif "update managed manifest version headers" in actions:
            _atomic_write(manifest_path, _json_bytes(_manifest_with_updated_headers(manifest)))

        packs = Path(__file__).parent / "schemas" / "standard-packs.json"
        target_packs = gov_dir / "standard-packs.json"
        if "create .governance/standard-packs.json" in actions:
            _atomic_write(target_packs, packs.read_bytes())

        if "write .governance/docs.json" in actions:
            docs_path = gov_dir / "docs.json"
            docs_content = render_adoption(path, item["repository"])
            _atomic_write(docs_path, docs_content.encode("utf-8"))
            lock_path = gov_dir / "manifest.lock.json"
            if "refresh docs.json digest in manifest.lock.json" in actions:
                lock = json.loads(lock_path.read_text(encoding="utf-8"))
                managed = lock.get("managedFiles")
                if isinstance(managed, dict):
                    managed[".governance/docs.json"] = hashlib.sha256(docs_content.encode("utf-8")).hexdigest()
                    _atomic_write(lock_path, _json_bytes(lock))

        # Local OneDev + Validator publication is the default for every
        # repository; an existing adopter restriction is kept.
        if "create .governance/local-ci-publication.json" in actions:
            local_ci = ensure_default_policy(path)
            if local_ci["changed"]:
                result["local_ci_publication"] = "created"
        if "register .governance/standard-requirements.json" in actions:
            registration = register(
                path, profiles=[target] if get_profile(target) else [],
                standards=[] if get_profile(target) else [target],
            )
            result["conformance"] = registration["conformance"]

        if sync_agents and any(action.startswith("project agent host instruction contracts (") for action in actions):
            agent_updates = sync_agent_instructions(path, item["repository"], overwrite=True)
            if agent_updates:
                result["agent_instructions"] = agent_updates

        result["status"] = "updated"
        results.append(result)
    return {"schema": REPORT_SCHEMA, "target": target, "repositories": results}


def _render_agent_instructions(
    repo_path: Path, host_id: str, repository_name: Optional[str] = None
) -> str:
    """Render the standard agent contract instructions for a specific host ID."""
    repo_line = f"- Repository: `{repository_name}`\n" if repository_name else ""
    header = (
        "<!-- wellmanifest:source-links:v1 -->\n"
        "## Managed standard sources\n\n"
        f"{repo_line}"
        "- Local adoption manifest: [.governance/manifest.json](.governance/manifest.json)\n"
        "- Host contract: [.governance/agent-hosts.json](.governance/agent-hosts.json)\n\n"
        "<!-- end wellmanifest:source-links:v1 -->\n\n"
    )
    contract_body = (
        "This repository follows the `wellmanifest/new-project` policy-as-code standard.\n"
        "Fail-closed. Do not write code until this contract is followed.\n\n"
        "1. Read `AGENTS.md` and `.governance/manifest.json`.\n"
        "2. Allocate tickets only through `./project/new-ticket.sh`. Never commit on `main` or a dirty primary checkout.\n"
        "3. Work in a canonical worktree v5 (`.worktrees/ticket-NNN--slug`).\n"
        "4. Stay inside that ticket's `intent.json` `allowedPaths`.\n"
        "5. Put every final result in the owning repository through its ticket: reports and analyses under `docs/` per `wellmanifest/docs`, error runbooks under `errors/` per `wellmanifest/logs`, and runtime leases under `.subactor/leases/`. Never leave outputs or state only in `~/.local/state`, `/tmp`, or scratchpads.\n"
        "6. Run `./project/governance-check.sh` before claiming done.\n"
    )

    if host_id == "generic":
        return f"# AGENTS.md\n\n{header}{contract_body}"
    elif host_id == "gemini":
        return f"# GEMINI.md\n\n{header}This file is the Gemini / Antigravity entry; the same rules are in `AGENTS.md`.\n\n{contract_body}"
    elif host_id == "claude":
        return f"# CLAUDE.md\n\n{header}This file is the Claude Code entry; the same rules are in `AGENTS.md`.\n\n{contract_body}"
    elif host_id == "cursor":
        return (
            "---\n"
            "description: Wellmanifest new-project standard governance rules\n"
            "globs: *\n"
            "alwaysApply: true\n"
            "---\n\n"
            f"# Cursor Standard Governance\n\n{contract_body}"
        )
    elif host_id == "copilot":
        return f"# GitHub Copilot Instructions\n\n{header}{contract_body}"
    return contract_body


def sync_agent_instructions(
    repo_path: Path,
    repository_name: Optional[str] = None,
    overwrite: bool = False,
) -> List[str]:
    """Synchronize standard instruction and learning files for all registered LLM agent hosts."""
    updated: List[str] = []
    agent_hosts_files = {
        "AGENTS.md": _render_agent_instructions(repo_path, "generic", repository_name=repository_name),
        "GEMINI.md": _render_agent_instructions(repo_path, "gemini", repository_name=repository_name),
        "CLAUDE.md": _render_agent_instructions(repo_path, "claude", repository_name=repository_name),
        ".cursor/rules/new-project-standard.mdc": _render_agent_instructions(repo_path, "cursor", repository_name=repository_name),
        ".github/copilot-instructions.md": _render_agent_instructions(repo_path, "copilot", repository_name=repository_name),
        ".aider.conf.yml": "read:\n  - AGENTS.md\n  - .governance/manifest.json\n",
    }
    for relative_path, content in agent_hosts_files.items():
        target = repo_path / relative_path
        new_bytes = content.encode("utf-8")
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(target, new_bytes)
            updated.append(relative_path)
        elif overwrite:
            existing = target.read_bytes()
            if existing != new_bytes:
                _atomic_write(target, new_bytes)
                updated.append(relative_path)

    # Configure local git hooks if .githooks directory exists
    githooks_dir = repo_path / ".githooks"
    git_dir = repo_path / ".git"
    if githooks_dir.is_dir() and (git_dir.is_dir() or git_dir.is_file()):
        try:
            subprocess.run(
                ["git", "-C", str(repo_path), "config", "--local", "core.hooksPath", ".githooks"],
                check=False,
                capture_output=True,
                timeout=5,
            )
        except Exception:
            pass

    return updated


def sync_fleet_agents(
    root: Path,
    recursive: Optional[bool] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Synchronize agent instructions across all discovered repositories in a fleet."""
    repositories: List[Dict[str, Any]] = []
    for path in discover_repositories(root, recursive):
        record = inspect_repository(path)
        updated = sync_agent_instructions(path, record.repository, overwrite=overwrite)
        repositories.append({
            "path": str(path),
            "repository": record.repository,
            "updated_files": updated,
            "status": "synchronized" if updated else "up-to-date",
        })
    return {
        "schema": "wellman.fleet-agent-sync/v1",
        "root": str(root.resolve()),
        "repositories": repositories,
        "synchronized_count": sum(1 for item in repositories if item["updated_files"]),
    }


def check_fleet(root: Path, recursive: Optional[bool] = None) -> Dict[str, Any]:
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


def check_monag_conflict(target_path: str) -> Optional[Dict[str, Any]]:
    """Check target path against MONAG conflict detection if monag is installed."""
    import shutil
    if not shutil.which("monag"):
        return None
    try:
        proc = subprocess.run(
            ["monag", "triage", "--limit", "1"],
            cwd=target_path,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode == 0 and "Declared conflict" in proc.stdout:
            return {"has_conflict": True, "details": "MONAG detected active scope conflict or lease"}
        return {"has_conflict": False}
    except Exception:
        return None


def emit_standardization_tickets(
    fleet_report: Dict[str, Any],
    koru_ready: bool = True,
    monag_triage: bool = False,
    taskand_ready: bool = False,
) -> Dict[str, Any]:
    """Convert fleet findings into blocked native admission requests.

    Produces a 'planfile.tickets/v1' structure where each non-compliant repository
    receives diagnostic context. Handoff flags select a requested adapter; they
    do not establish native ownership, a fenced lease or execution authority.
    """
    tickets: List[Dict[str, Any]] = []

    for repo_entry in fleet_report.get("repositories", []):
        findings = repo_entry.get("findings", [])
        if not findings:
            continue

        repo_path = repo_entry.get("path")
        repo_name = repo_entry.get("repository") or (Path(repo_path).name if repo_path else "unknown")
        error_findings = [f for f in findings if f.get("severity") == "ERROR"]
        warn_findings = [f for f in findings if f.get("severity") == "WARNING"]

        if not error_findings and not warn_findings:
            continue

        codes = sorted(list({f.get("code") for f in error_findings + warn_findings if f.get("code")}))
        codes_str = ", ".join(codes[:3]) + ("..." if len(codes) > 3 else "")
        priority = "critical" if error_findings else "medium"
        tier = "floor" if priority == "critical" else "hygiene"

        title = f"[STANDARDIZATION] {repo_name}: fix conformance ({codes_str})"

        desc_lines = [
            f"**Repository**: `{repo_name}` ({repo_path})",
            f"**Standardization Findings**: {len(findings)} detected ({len(error_findings)} errors, {len(warn_findings)} warnings)",
            "",
            "### Detected Non-Compliance:",
        ]
        for f in findings:
            desc_lines.append(f"- `[{f.get('code')}]` ({f.get('severity')}) {f.get('message')}")
            if f.get("remediation"):
                desc_lines.append(f"  *Remediation*: {f.get('remediation')}")

        desc_lines.extend([
            "",
            "### Satisfied When:",
            "- The native owner admits a bounded ticket, worktree and fenced lease.",
            "- Applicable implemented checks and exact-head protected verification pass.",
            "",
            "### Remediation Guidance:",
            "- Reconcile immutable standard pins through the native adoption process.",
            "- Work inside a designated Wellmanifest worktree v5.",
            "- Validate clean conformance before commit.",
        ])

        parent_ticket_id = f"GOV-{hashlib.sha256(f'{repo_name}:{repo_path}'.encode()).hexdigest()[:8]}"
        remediation_ticket_id = f"{parent_ticket_id}-1-remediate"
        cicd_ticket_id = f"{parent_ticket_id}-2-cicd"

        # Parent / Epic coordination ticket
        ticket: Dict[str, Any] = {
            "id": parent_ticket_id,
            "name": title,
            "title": title,
            "description": "\n".join(desc_lines),
            "priority": priority,
            "tier": tier,
            "labels": ["wellmanifest", "standardization"],
            "target_repo": repo_name,
            "target_path": repo_path,
            "findings_count": len(findings),
            "source": {"tool": "wellman"},
            "schema": "planfile.tickets/v1",
            "children": [],
            "execution": {
                "queue": "governance-handoff",
                "state": "blocked",
                "last_error": "native_admission_required",
            },
            "remediation_request": {
                "status": "admission_required",
                "objective": f"Remediate Wellmanifest standard compliance findings for {repo_name}",
                "findings": findings,
            },
            "strategy": {
                "phases": ["remediation", "ci_cd_verification"],
                "deliverables": [".governance/manifest.json", ".governance/standard-packs.json", ".governance/manifest.lock.json"],
                "gate_argv": ["wellman", "check", "--root", repo_path],
            },
        }

        if monag_triage and repo_path:
            conflict = check_monag_conflict(repo_path)
            if conflict:
                ticket["monag_conflict"] = conflict
                if conflict.get("has_conflict"):
                    ticket["labels"].append("monag:scope-conflict")

        if koru_ready or taskand_ready:
            active_executor = "taskand" if taskand_ready else "koru"
            ticket["labels"].extend([f"{active_executor}-refactor", "governance-handoff"])
            if taskand_ready:
                ticket["labels"].append("taskand-job")
            ticket["requested_executor"] = active_executor
            ticket["children"] = [remediation_ticket_id, cicd_ticket_id]
            ticket["source_tool"] = "wellman-fleet-watcher"

            # Subtask 1: Concrete remediation task
            remediation_subtask: Dict[str, Any] = {
                "id": remediation_ticket_id,
                "parent": parent_ticket_id,
                "name": f"[REMEDIATION] {repo_name}: apply wellmanifest adoption",
                "title": f"[REMEDIATION] {repo_name}: apply wellmanifest adoption",
                "description": f"Bootstrap governance baseline for {repo_name} using wellman adopt.",
                "priority": priority,
                "tier": tier,
                "labels": ["wellmanifest", "standardization", "subtask:remediation"],
                "target_repo": repo_name,
                "target_path": repo_path,
                "requested_executor": active_executor,
                "execution": dict(ticket["execution"]),
                "schema": "planfile.tickets/v1",
            }

            # Subtask 2: CI/CD validation and verification gate
            cicd_subtask: Dict[str, Any] = {
                "id": cicd_ticket_id,
                "parent": parent_ticket_id,
                "blocked_by": [remediation_ticket_id],
                "name": f"[CI/CD] {repo_name}: verify standards gate & pipeline conformance",
                "title": f"[CI/CD] {repo_name}: verify standards gate & pipeline conformance",
                "description": f"Run complete governance gate checks and verify CI/CD readiness for {repo_name}.",
                "priority": priority,
                "tier": tier,
                "labels": ["wellmanifest", "standardization", "subtask:cicd", "qa"],
                "target_repo": repo_name,
                "target_path": repo_path,
                "requested_executor": active_executor,
                "execution": dict(ticket["execution"]),
                "schema": "planfile.tickets/v1",
            }

            tickets.append(remediation_subtask)
            tickets.append(cicd_subtask)

        tickets.append(ticket)

    for ticket in tickets:
        # Native Planfile imports allocate fresh IDs. Keep proposal identity and
        # relationships as advisory context until the native owner admits a DAG.
        ticket["status"] = "blocked"
        ticket["source"] = {
            "tool": "wellman",
            "context": {
                "native_admission_required": True,
                "request_id": ticket["id"],
                "target_repo": ticket["target_repo"],
                "target_path": ticket["target_path"],
                "requested_executor": ticket.get("requested_executor"),
                "requested_parent": ticket.get("parent"),
                "requested_children": ticket.get("children", []),
                "requested_blocked_by": ticket.get("blocked_by", []),
            },
        }

    return {
        "schema": "planfile.tickets/v1",
        "source": "wellman.fleet-check",
        "count": len(tickets),
        "tickets": tickets,
    }


def feed_to_planfile(
    tickets_doc: Dict[str, Any],
    planfile_project: Optional[Path] = None,
    per_repo: bool = True,
    *, selection_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Feed generated standardization tickets into Planfile if available.

    Pipes the ticket list directly as JSON to satisfy Planfile schema validation.
    If per_repo is True and repositories have local .planfile directories,
    tickets are distributed to their respective repositories. Otherwise, tickets
    are imported into planfile_project or current working directory.
    """
    if tickets_doc.get("schema") == "wellman.selection-plan/v1":
        return _export_selection_backlog(tickets_doc, planfile_project, selection_context)
    import shutil
    if not shutil.which("planfile"):
        return {"ok": False, "error": "planfile executable not found on PATH"}

    tickets = tickets_doc.get("tickets", [])
    if not tickets:
        return {"ok": True, "count": 0, "output": "no tickets to import", "target_projects": []}

    if tickets_doc.get("source") == "wellman.fleet-check":
        # Bulk import does not remap our proposal IDs. Never install dangling
        # runtime dependencies; the source context retains the requested graph.
        tickets = [
            {key: value for key, value in ticket.items()
             if key not in {"parent", "children", "blocked_by"}}
            for ticket in tickets
        ]

    target_projects: List[str] = []

    # If an explicit central project was given and not per_repo mode:
    if planfile_project is not None and not per_repo:
        cmd = ["planfile", "ticket", "import", "--source", "wellman"]
        try:
            input_data = json.dumps(tickets)
            proc = subprocess.run(
                cmd,
                input=input_data,
                cwd=str(planfile_project),
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if proc.returncode != 0:
                return {"ok": False, "error": proc.stderr.strip() or f"exit code {proc.returncode}"}
            return {
                "ok": True,
                "count": len(tickets),
                "output": proc.stdout.strip(),
                "target_projects": [str(planfile_project)],
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # Group tickets by target repo if possible
    repo_tickets: Dict[Path, List[Dict[str, Any]]] = {}
    default_dir = planfile_project if planfile_project else Path.cwd()

    for t in tickets:
        target_path_str = t.get("target_path")
        target_dir = Path(target_path_str) if target_path_str else default_dir
        if (target_dir / ".planfile").is_dir() or (target_dir / "planfile.yaml").is_file():
            repo_tickets.setdefault(target_dir, []).append(t)
        else:
            repo_tickets.setdefault(default_dir, []).append(t)

    imported_count = 0
    errors: List[str] = []

    for target_dir, tkts in repo_tickets.items():
        cmd = ["planfile", "ticket", "import", "--source", "wellman"]
        try:
            input_data = json.dumps(tkts)
            proc = subprocess.run(
                cmd,
                input=input_data,
                cwd=str(target_dir),
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if proc.returncode != 0:
                errors.append(f"{target_dir.name}: {proc.stderr.strip()}")
            else:
                imported_count += len(tkts)
                target_projects.append(str(target_dir))
        except Exception as exc:
            errors.append(f"{target_dir.name}: {exc}")

    if errors and imported_count == 0:
        return {"ok": False, "error": "; ".join(errors), "target_projects": target_projects}
    return {
        "ok": True,
        "count": imported_count,
        "target_projects": target_projects,
        "errors": errors if errors else None,
    }


def trigger_koru_execution(
    project_path: Path,
    queue_name: str = "governance-handoff",
    dry_run: bool = False,
    max_iterations: int = 10,
) -> Dict[str, Any]:
    """Trigger autonomous koru queue drain on the target project."""
    import shutil
    if not shutil.which("koru"):
        return {"ok": False, "error": "koru executable not found on PATH"}

    cmd = [
        "koru",
        "--queue",
        "--loop",
        "--queue-name",
        queue_name,
        "--project",
        str(project_path),
        "--max-iterations",
        str(max_iterations),
    ]
    if dry_run:
        cmd.append("--dry-run")

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def trigger_taskand_execution(
    project_path: Path,
    queue_name: str = "governance-handoff",
    dry_run: bool = False,
    engine_runner: Optional[Any] = None,
) -> Dict[str, Any]:
    """Dispatch through an explicitly bound native engine, never a shell fallback.

    The caller-supplied engine owns native admission and effect verification.
    Imported ticket metadata cannot establish that boundary by itself.
    """
    planfile_tickets = project_path / ".planfile" / "tickets.json"
    if not planfile_tickets.is_file():
        # Check tickets in repo root
        planfile_tickets = project_path / "planfile-tickets.json"

    tickets_data: List[Dict[str, Any]] = []
    if planfile_tickets.is_file():
        try:
            loaded = json.loads(planfile_tickets.read_text(encoding="utf-8"))
            tickets_data = loaded if isinstance(loaded, list) else loaded.get("tickets", [])
        except Exception:
            pass

    if callable(engine_runner):
        return engine_runner(
            project_path,
            queue_name=queue_name,
            dry_run=dry_run,
            tickets=tickets_data,
        )

    return {
        "ok": dry_run,
        "dry_run": dry_run,
        "executed": False,
        "status": "blocked",
        "error": "native_admission_required",
        "executor": "taskand",
        "queue": queue_name,
        "project": str(project_path),
        "tickets_found": len(tickets_data),
        "operations_planned": [],
        "steps": [],
        "commit": None,
    }



def _export_selection_backlog(plan, project, context):
    """Pinned native Planfile adapter; only explicit local review backlog effects.

    The public dedupe method reopens completed keys. This adapter deliberately
    uses the same native locked allocator/store primitives to preserve every
    terminal state, and fails closed on an unsupported optional API version.
    It does not invoke a runner, synchronizer, shell executor or remote adapter.
    """
    from wellman.selection_contracts import ContractError, payload_digest
    from wellman.selection_plan import assert_plan_current, assert_repository_current

    if project is None or not isinstance(context, dict):
        return {
            "ok": False,
            "error": "Explicit Planfile project and selection context required",
        }

    def check():
        assert_plan_current(
            plan, context["observation"], context["catalog"], context["adoptions"]
        )
        assert_repository_current(
            context["observation"],
            context["adoptions"],
            context["repository_roots"],
            inventory_options=context.get("inventory_options"),
            artifact_root=context.get("artifact_root"),
        )

    try:
        check()
        import planfile

        if getattr(planfile, "__version__", None) != "0.1.126":
            raise ContractError(
                "Unsupported Planfile adapter version; expected 0.1.126"
            )
        from planfile.core.models import Ticket
        from planfile.core.store import Store

        for name in (
            "mutation_lock",
            "ticket_records",
            "get_ticket",
            "_reserve_ids_unlocked",
            "_create_tickets_bulk_unlocked",
            "_update_ticket_unlocked",
        ):
            if not callable(getattr(Store, name, None)):
                raise ContractError(
                    "Unsupported native Planfile store capability: " + name
                )
        project = Path(project).absolute()
        for source_root in context["repository_roots"].values():
            source_root = Path(source_root).absolute()
            if project == source_root or source_root in project.parents:
                raise ContractError(
                    "Use a Planfile project outside the observed source tree"
                )
        # Reject symlink storage before the optional dependency can write to it.
        if any(p.is_symlink() for p in (project, *project.parents)):
            raise ContractError("Planfile project must not traverse symlinks")
        storage = project / ".planfile"
        if storage.exists() and any(p.is_symlink() for p in storage.rglob("*")):
            raise ContractError("Planfile storage contains a symlink")
        if storage.is_symlink():
            raise ContractError("Planfile storage is a symlink")
        selected = [d for d in plan["decisions"] if d["action"] != "keep"]
        if not selected:
            return {
                "ok": True,
                "count": 0,
                "created": 0,
                "tickets": [],
                "target_projects": [],
                "remote_effects": False,
                "executable": False,
            }

        def key(d):
            return payload_digest(
                {
                    k: d[k]
                    for k in (
                        "repository_id",
                        "component_id",
                        "standard_id",
                        "scope",
                        "target_revision",
                    )
                }
            )

        keys = [key(d) for d in selected]
        if len(set(keys)) != len(keys):
            raise ContractError("Duplicate selection proposal identity")
        store = Store(project)
        if store.project_dir != project:
            raise ContractError(
                "Explicit project resolves to another Planfile boundary"
            )
        rows = []
        allocated = []
        terminal = {"done", "canceled", "failed", "blocked"}
        with store.mutation_lock():
            # Revalidate after waiting for the native cross-process lock.
            check()
            if not store.is_initialized():
                store.init()
            records = list(store.ticket_records(sprint="all"))
            existing = {}
            for k in keys:
                matches = [
                    r
                    for r in records
                    if "dedupe:wellman-selection:" + k in (r.get("labels") or [])
                ]
                if len(matches) > 1:
                    raise ContractError("Ambiguous existing proposal key")
                if matches:
                    t = store.get_ticket(matches[0]["id"], repair_index=False)
                    if t is None:
                        raise ContractError("Proposal disappeared from native store")
                    existing[k] = t
            # Reserve the whole missing set under the native lock, then persist
            # once with final dependencies. Per-ticket creation repeatedly
            # rewrites the entire sprint and invokes advisory enrichment.
            missing = [(k, d) for k, d in zip(keys, selected) if k not in existing]
            ids = store._reserve_ids_unlocked(len(missing)) if missing else []
            if len(ids) != len(missing) or len(set(ids)) != len(ids):
                raise ContractError("Native batch allocation returned invalid identities")
            for (k, d), ticket_id in zip(missing, ids):
                t = Ticket(
                    id=ticket_id,
                    name="Review " + d["action"] + ": " + d["standard_id"],
                    status="open",
                    sprint="backlog",
                    labels=sorted([
                        "wellman-selection",
                        "actor:human",
                        "autonomy-frontier",
                        "dedupe:wellman-selection:" + k,
                    ]),
                    executor={"kind": "human", "mode": "interactive"},
                    execution={
                        "queue": "wellman-selection-review",
                        "state": "pending",
                    },
                    source={
                        "tool": "wellman.selection-plan",
                        "version": "v1",
                        "context": {
                            "plan_hash": plan["plan_hash"],
                            "proposal": d,
                            "grants_authority": False,
                        },
                    },
                )
                existing[k] = t
                allocated.append(k)

            def dependency_ids(decision):
                return sorted({
                    existing[key(other)].id
                    for other in selected
                    if other["repository_id"] == decision["repository_id"]
                    and other["standard_id"] in decision["depends_on"]
                    and (other["scope"] in ("repository", "workspace")
                         or other["component_id"] == decision["component_id"])
                })

            created = []
            for k, d in missing:
                existing[k].blocked_by = dependency_ids(d)
                created.append(existing[k])
            if created:
                store._create_tickets_bulk_unlocked(created)
            for k, d in zip(keys, selected):
                t = existing[k]
                state = str(getattr(t.status, "value", t.status))
                if state in terminal:
                    rows.append({"id": t.id, "state": "preserved_terminal", "key": k})
                    continue
                if (
                    state != "open"
                    or t.executor is None
                    or (t.executor.kind, t.executor.mode) != ("human", "interactive")
                    or t.execution is None
                    or t.execution.state != "pending"
                    or t.execution.queue != "wellman-selection-review"
                    or any(
                        getattr(t.execution, field) is not None
                        for field in (
                            "assigned_to",
                            "started_at",
                            "finished_at",
                            "lease_expires_at",
                        )
                    )
                    or t.source is None
                    or t.source.tool != "wellman.selection-plan"
                    or t.source.version != "v1"
                    or t.source.context.get("grants_authority") is not False
                    or t.inputs is not None
                    or not {"wellman-selection", "actor:human", "autonomy-frontier"}
                    <= set(t.labels)
                ):
                    rows.append({"id": t.id, "state": "preserved_owned", "key": k})
                    continue
                deps = dependency_ids(d)
                source = t.source.model_dump(mode="json")
                source["context"] = {
                    **source["context"],
                    "plan_hash": plan["plan_hash"],
                    "proposal": d,
                    "grants_authority": False,
                }
                labels = sorted(set(t.labels) | {"actor:human", "autonomy-frontier"})
                changed = (
                    source != t.source.model_dump(mode="json")
                    or deps != t.blocked_by
                    or labels != t.labels
                )
                if changed:
                    updated = store._update_ticket_unlocked(
                        t.id,
                        expected_updated_at=t.updated_at.isoformat(),
                        reason="Refresh evidence-bound review proposal",
                        actor="wellman.selection-export",
                        source=source,
                        blocked_by=deps,
                        labels=labels,
                    )
                    if updated is None:
                        raise ContractError(
                            "Proposal update lost its expected revision"
                        )
                rows.append(
                    {
                        "id": t.id,
                        "state": "created"
                        if k in allocated
                        else "updated"
                        if changed
                        else "reused",
                        "key": k,
                    }
                )
        return {
            "ok": True,
            "count": len(rows),
            "created": len(allocated),
            "tickets": rows,
            "target_projects": [str(project)],
            "remote_effects": False,
            "executable": False,
        }
    except (
        ImportError,
        ContractError,
        KeyError,
        ValueError,
        OSError,
        RuntimeError,
    ) as exc:
        return {"ok": False, "error": str(exc), "remote_effects": False}
