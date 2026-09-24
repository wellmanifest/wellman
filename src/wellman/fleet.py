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
    missing_agents = [f for f in ["AGENTS.md", "GEMINI.md", "CLAUDE.md"] if not (record.path / f).exists()]
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

        if sync_agents:
            agent_updates = sync_agent_instructions(path, item["repository"])
            if agent_updates:
                result["agent_instructions"] = agent_updates

        result["status"] = "updated"
        results.append(result)
    return {"schema": REPORT_SCHEMA, "target": target, "repositories": results}


def _render_agent_instructions(repo_path: Path, host_id: str) -> str:
    """Render the standard agent contract instructions for a specific host ID."""
    header = (
        "<!-- wellmanifest:source-links:v1 -->\n"
        "## Managed standard sources\n\n"
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
        "5. Run `./project/governance-check.sh` before claiming done.\n"
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


def sync_agent_instructions(repo_path: Path, repository_name: Optional[str] = None) -> List[str]:
    """Synchronize standard instruction and learning files for all registered LLM agent hosts."""
    updated: List[str] = []
    agent_hosts_files = {
        "AGENTS.md": _render_agent_instructions(repo_path, "generic"),
        "GEMINI.md": _render_agent_instructions(repo_path, "gemini"),
        "CLAUDE.md": _render_agent_instructions(repo_path, "claude"),
        ".cursor/rules/new-project-standard.mdc": _render_agent_instructions(repo_path, "cursor"),
        ".github/copilot-instructions.md": _render_agent_instructions(repo_path, "copilot"),
        ".aider.conf.yml": "read:\n  - AGENTS.md\n  - .governance/manifest.json\n",
    }
    for relative_path, content in agent_hosts_files.items():
        target = repo_path / relative_path
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(target, content.encode("utf-8"))
            updated.append(relative_path)
    return updated


def sync_fleet_agents(root: Path, recursive: Optional[bool] = None) -> Dict[str, Any]:
    """Synchronize agent instructions across all discovered repositories in a fleet."""
    repositories: List[Dict[str, Any]] = []
    for path in discover_repositories(root, recursive):
        record = inspect_repository(path)
        updated = sync_agent_instructions(path, record.repository)
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
) -> Dict[str, Any]:
    """Convert fleet check findings into actionable, Planfile/Koru-compatible tickets.

    Produces a 'planfile.tickets/v1' structure where each non-compliant repository
    receives an actionable ticket with diagnostic findings and remediation steps.
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
            f"- `wellman check --root {repo_path}` exits with code 0 (no ERROR findings).",
            "",
            "### Remediation Guidance:",
            "- Adopt missing standard packs via `wellman adopt` or sync `.governance/` files.",
            "- Work inside a designated Wellmanifest worktree v5.",
            "- Validate clean conformance before commit.",
        ])

        ticket: Dict[str, Any] = {
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
        }

        if monag_triage and repo_path:
            conflict = check_monag_conflict(repo_path)
            if conflict:
                ticket["monag_conflict"] = conflict
                if conflict.get("has_conflict"):
                    ticket["labels"].append("monag:scope-conflict")

        if koru_ready:
            ticket["labels"].extend(["koru-refactor", "governance-handoff"])
            ticket["executor"] = {"kind": "shell", "mode": "autonomous"}
            ticket["executor_kind"] = "koru"
            ticket["executor_mode"] = "autonomous"
            ticket["inputs"] = {
                "script": f"wellman adopt --root '{repo_path}' wellmanifest/new-project && wellman check --root '{repo_path}'",
                "expect_files_changed": True,
            }
            ticket["execution"] = {
                "queue": "governance-handoff",
                "state": "ready",
            }
            ticket["source_tool"] = "wellman-fleet-watcher"
            ticket["remediation_intent"] = {
                "schema": "new-project.remediation-intent/v1",
                "repository": repo_name,
                "status": "READY",
                "objective": f"Remediate Wellmanifest standard compliance findings for {repo_name}",
                "findings": findings,
            }

        tickets.append(ticket)

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
) -> Dict[str, Any]:
    """Feed generated standardization tickets into Planfile if available.

    Pipes the ticket list directly as JSON to satisfy Planfile schema validation.
    If per_repo is True and repositories have local .planfile directories,
    tickets are distributed to their respective repositories. Otherwise, tickets
    are imported into planfile_project or current working directory.
    """
    import shutil
    if not shutil.which("planfile"):
        return {"ok": False, "error": "planfile executable not found on PATH"}

    tickets = tickets_doc.get("tickets", [])
    if not tickets:
        return {"ok": True, "count": 0, "output": "no tickets to import", "target_projects": []}

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

