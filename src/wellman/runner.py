"""Standard Conformance Runner.

Executes deterministic checks across all Wellmanifest standards:
- Git lifecycle (branches, commit scope, intent)
- Worktrees (naming, placement, overlap detection)
- Ticket lifecycle (intent, activity, allocations)
- Agent & host contracts (AGENTS.md, host bindings)
- Canonical governance gate delegation
"""

from __future__ import annotations

import json
import hashlib
import os
import re
import runpy
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from wellman.validator import Finding, StandardsValidator


def _find_bundled_script(script_name: str) -> Optional[Path]:
    """Find a canonical checker script in _bundled/."""
    p = Path(__file__).parent / "_bundled" / script_name
    return p if p.is_file() else None


def _adopted_checker(root: Path, relative: str, required=()) -> Optional[Path]:
    """Check the adopter's pinned checker and its managed governance dependencies."""
    from wellman.adoption import safe_path

    checker = root / relative
    lock_candidate = root / ".governance/manifest.lock.json"
    if not checker.exists() and not checker.is_symlink() and not lock_candidate.exists() and not lock_candidate.is_symlink():
        return _find_bundled_script(checker.name)
    lock_path = safe_path(lock_candidate)
    lock = json.loads(lock_path.read_text())
    managed = lock.get("managedFiles")
    if not isinstance(managed, dict) or not {relative, *required} <= managed.keys():
        raise ValueError("Adopted checker dependency pins are missing")
    for relative, expected in managed.items():
        if not isinstance(relative, str) or not relative.startswith(".governance/"):
            continue
        path = safe_path(root / relative)
        if not path.is_relative_to(root) or not isinstance(expected, str) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Adopted governance bytes do not match their immutable pins")
    return safe_path(checker)


_CANONICAL_WORKTREE = re.compile(
    r"^ticket-(?P<number>[0-9]{3,})--(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)$"
)
_CANONICAL_BRANCH = re.compile(
    r"^refs/heads/ticket/(?P<number>[0-9]{3,})-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)$"
)


def _git_environment():
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def _git_worktree_records(root: Path) -> list[dict[str, str]]:
    """Read Git's registered worktrees without repairing or mutating them."""
    result = subprocess.run(
        ["git", "-C", str(root), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
        env=_git_environment(),
    )
    if result.returncode != 0:
        raise ValueError("Git could not enumerate registered worktrees")

    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in result.stdout.splitlines() + [""]:
        if not line:
            if current.get("path"):
                records.append(current)
            current = {}
            continue
        key, _, value = line.partition(" ")
        if key in {"worktree", "branch"}:
            current["path" if key == "worktree" else key] = value
    return records


def _absorbed_submodule_admitted(root: Path) -> bool:
    """Verify an absorbed primary against Git's actual parent registration.

    Git can list the module administration directory as its primary worktree.
    A gitfile alone is insufficient: the parent must admit the checkout, track
    its gitlink, and own the module metadata with the correct core.worktree.
    """
    def observe(checkout: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(checkout), *arguments],
            capture_output=True, text=True, check=False, timeout=10,
            env=_git_environment(),
        )
        if result.returncode != 0:
            raise ValueError("Git could not verify absorbed submodule registration")
        return result.stdout.strip()

    if not (root / ".git").is_file():
        return False
    parent_value = observe(root, "rev-parse", "--show-superproject-working-tree")
    if not parent_value:
        return False
    parent = Path(parent_value).resolve()
    relative = root.relative_to(parent).as_posix()
    if root == parent or _worktree_admission(parent) is not None:
        return False

    entries = observe(parent, "ls-files", "--stage", "-z", "--", relative).split("\0")
    entries = [entry for entry in entries if entry]
    if len(entries) != 1:
        return False
    metadata, separator, path = entries[0].partition("\t")
    if not separator or not metadata.startswith("160000 ") or path != relative:
        return False

    git_dir = Path(observe(root, "rev-parse", "--absolute-git-dir")).resolve()
    common = Path(observe(root, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
    module_path = Path(observe(parent, "rev-parse", "--git-path", "modules"))
    module_root = (parent / module_path).resolve()
    if git_dir == module_root or not git_dir.is_relative_to(module_root) or git_dir != common:
        return False
    configured = Path(observe(root, "config", "--get", "core.worktree"))
    return (git_dir / configured).resolve() == root


def _worktree_admission(root: Path) -> Optional[Finding]:
    """Reject execution from an unregistered or system-temporary checkout.

    A plain clone is a valid Git repository from Git's perspective, so Git
    alone cannot distinguish it from the adopter's primary checkout. The
    explicit system-temp rejection closes the failure mode that caused agents
    to work from ``/tmp``; linked delivery worktrees additionally require the
    v5 directory/branch identity.
    """
    try:
        if root == Path("/tmp") or Path("/tmp") in root.parents:
            return Finding(
                code="GOV-WORKTREE-ADMISSION-001",
                message="Refusing to run from a Git checkout below /tmp.",
                path=str(root),
                remediation="Use the registered primary or an allocated canonical ticket worktree.",
            )
        top_level = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            env=_git_environment(),
        )
        if top_level.returncode != 0:
            raise ValueError("Git checkout is not readable")
        observed_root = Path(top_level.stdout.strip()).resolve()
        if observed_root != root:
            raise ValueError("requested root is not the Git checkout root")

        records = _git_worktree_records(root)
        canonical_root = next(
            (Path(record["path"]).resolve() for record in records
             if Path(record["path"]).resolve() == root),
            None,
        )
        if canonical_root is None:
            if _absorbed_submodule_admitted(root):
                return None
            return Finding(
                code="GOV-WORKTREE-ADMISSION-002",
                message="Checkout is not registered in Git's worktree set.",
                path=str(root),
                remediation=(
                    "Use git worktree add --relative-paths from the registered "
                    "primary checkout; do not use a standalone clone."
                ),
            )

        primary = Path(records[0]["path"]).resolve() if records else None
        if primary is None or root == primary:
            return None

        try:
            relative = root.relative_to(primary / ".worktrees")
        except ValueError:
            return Finding(
                code="GOV-WORKTREE-ADMISSION-003",
                message="Linked checkout is outside the canonical .worktrees directory.",
                path=str(root),
                remediation="Use <primary>/.worktrees/ticket-NNN--slug.",
            )
        if len(relative.parts) != 1:
            return Finding(
                code="GOV-WORKTREE-ADMISSION-003",
                message="Linked checkout is nested below the canonical .worktrees directory.",
                path=str(root),
                remediation="Use one direct <primary>/.worktrees/ticket-NNN--slug directory.",
            )

        directory_match = _CANONICAL_WORKTREE.fullmatch(relative.name)
        branch = next(
            (record.get("branch") for record in records
             if Path(record["path"]).resolve() == root),
            None,
        )
        branch_match = _CANONICAL_BRANCH.fullmatch(branch or "")
        if not directory_match or not branch_match or directory_match.groupdict() != branch_match.groupdict():
            return Finding(
                code="GOV-WORKTREE-ADMISSION-004",
                message="Linked checkout directory and ticket branch do not share a v5 identity.",
                path=str(root),
                remediation="Use ticket-NNN--slug with branch ticket/NNN-slug.",
            )
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        return Finding(
            code="GOV-WORKTREE-ADMISSION-005",
            message=f"Cannot verify canonical worktree admission: {error}",
            path=str(root),
            remediation="Re-enter through the Wellmanifest allocator and registered worktree.",
        )
    return None


class ConformanceRunner:
    """Runs conformance checks across all adopted standards."""

    def __init__(self, root: Path):
        self.requested_root = Path(root)
        self.root = root.resolve()
        self.validator = StandardsValidator(self.root)

    def check_git_lifecycle(self) -> List[Finding]:
        """Validate wellmanifest/git-lifecycle standard compliance."""
        findings: List[Finding] = []
        # Check current branch
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(self.root),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                branch = res.stdout.strip()
                # If branch is not main/master, check ticket binding format
                if branch not in ("main", "master", "HEAD"):
                    ticket_pattern = re.compile(r"^(ticket/(\d+|PLF-\d+)|feature/|fix/|chore/|release/|governance/)")
                    if not ticket_pattern.match(branch):
                        findings.append(Finding(
                            code="GOV-GIT-001",
                            message=f"Branch '{branch}' does not conform to Wellmanifest git-lifecycle naming.",
                            severity="WARNING",
                            path=f"branch:{branch}",
                            remediation="Use conventional branch prefix: ticket/NNN-*, ticket/PLF-NNN-*, feature/*, fix/*, chore/*, or release/*.",
                        ))
        except Exception as e:
            findings.append(Finding("GOV-GIT-ERROR", f"Git check error: {e}", severity="WARNING"))

        return findings

    def check_worktrees(self) -> List[Finding]:
        """Validate wellmanifest/worktrees standard compliance."""
        from wellman.adoption import safe_path

        try:
            safe_path(self.requested_root)
        except (OSError, ValueError) as error:
            return [Finding("GOV-WORKTREE-ADMISSION-005", str(error), path=str(self.requested_root))]
        admission = _worktree_admission(self.root)
        if admission is not None:
            return [admission]
        findings: List[Finding] = []
        worktrees_dir = self.root / ".worktrees"

        # Check bundled worktree overlap check if available
        try:
            checker = _adopted_checker(self.root, ".governance/worktree_overlap_check.py", (
                ".governance/worktree_path_check.py", ".governance/worktrees.schema.json",
                ".governance/ticket_activity.py",
            ))
        except (OSError, ValueError, TypeError) as error:
            return [Finding("GOV-WORKTREE-CHECK-001", f"Cannot verify the required checker: {error}")]
        if checker is None:
            findings.append(Finding(
                code="GOV-WORKTREE-CHECK-001",
                message="Required worktree overlap checker is unavailable.",
                remediation="Restore the installed checker before claiming conformance.",
            ))
        else:
            try:
                res = subprocess.run(
                    [sys.executable, str(checker), "--workspace-root", str(self.root),
                     "--identity-of", str(self.root), "--format", "json"],
                    cwd=str(self.root),
                    capture_output=True,
                    text=True,
                    timeout=15,
                    env=_git_environment(),
                )
                if res.returncode != 0:
                    diagnostic = (res.stdout + "\n" + res.stderr).strip()[:2000]
                    findings.append(Finding(
                        code="GOV-WORKTREE-OVERLAP-001",
                        message=f"Worktree overlap checker exited {res.returncode}: {diagnostic or 'no diagnostic output'}",
                        remediation="Resolve the checker failure or reported overlap before continuing.",
                    ))
                else:
                    report = json.loads(res.stdout)
                    summary = report.get("summary", {}) if isinstance(report, dict) else {}
                    if (not isinstance(report, dict)
                            or report.get("schema") != "new-project.worktree-overlap-report/v1"
                            or report.get("status") != "passed" or report.get("findings") != []
                            or not isinstance(summary, dict)
                            or any(type(summary.get(key)) is not int or summary[key] != 0 for key in ("errors", "warnings", "findings"))
                            or type(summary.get("checkouts")) is not int or summary["checkouts"] < 1):
                        raise ValueError("Checker did not prove a completed passing observation")
            except (OSError, subprocess.SubprocessError, UnicodeError) as error:
                findings.append(Finding(
                    code="GOV-WORKTREE-CHECK-002",
                    message=f"Cannot execute the required worktree checker: {type(error).__name__}: {str(error)[:2000]}",
                    remediation="Restore checker access and execution; an unavailable observation cannot pass.",
                ))
            except (ValueError, TypeError) as error:
                findings.append(Finding(
                    code="GOV-WORKTREE-CHECK-004",
                    message="Worktree checker returned an invalid or incomplete success report.",
                    remediation="Restore the pinned report contract; exit zero alone does not prove conformance.",
                ))

        if worktrees_dir.is_dir():
            for entry in worktrees_dir.iterdir():
                if entry.is_dir():
                    # Validate canonical worktree naming
                    if not entry.name.startswith("ticket-") and not entry.name.startswith("."):
                        findings.append(Finding(
                            code="GOV-WORKTREE-001",
                            message=f"Worktree directory '{entry.name}' does not follow canonical naming 'ticket-NNN--slug'.",
                            severity="WARNING",
                            path=str(entry.relative_to(self.root)),
                            remediation="Use `git worktree add .worktrees/ticket-NNN--slug`.",
                        ))

        return findings

    def check_ticket_lifecycle(self) -> List[Finding]:
        """Validate wellmanifest/ticket-lifecycle standard compliance."""
        findings: List[Finding] = []
        project_dir = self.root / "project"

        if project_dir.is_dir():
            for entry in project_dir.iterdir():
                if entry.is_dir() and entry.name.startswith("ticket-"):
                    intent_file = entry / "intent.json"
                    readme_file = entry / "README.md"

                    if not readme_file.is_file():
                        findings.append(Finding(
                            code="GOV-TICKET-README",
                            message=f"Ticket directory '{entry.name}' is missing README.md",
                            path=str(entry.relative_to(self.root)),
                            remediation="Create README.md describing the ticket scope and acceptance criteria.",
                        ))

                    if not intent_file.is_file():
                        findings.append(Finding(
                            code="GOV-TICKET-INTENT",
                            message=f"Ticket directory '{entry.name}' is missing intent.json",
                            severity="WARNING",
                            path=str(entry.relative_to(self.root)),
                            remediation="Initialize intent.json with bounded change budget and scope.",
                        ))

        return findings

    def check_agent_hosts(self) -> List[Finding]:
        """Validate wellmanifest/agent standard compliance."""
        findings: List[Finding] = []
        agents_md = self.root / "AGENTS.md"
        hosts_json = self.root / ".governance" / "agent-hosts.json"

        if not agents_md.is_file():
            findings.append(Finding(
                code="GOV-AGENT-001",
                message="Missing AGENTS.md instruction file in repository root.",
                severity="WARNING",
                path="AGENTS.md",
                remediation="Generate AGENTS.md from the Wellmanifest template.",
            ))

        return findings

    def run_all(self) -> List[Finding]:
        """Execute validation across all standards."""
        findings: List[Finding] = []
        # 1. Structural schema & manifest validations
        findings.extend(self.validator.run_all_validations())
        # 2. Git lifecycle checks
        findings.extend(self.check_git_lifecycle())
        # 3. Worktree checks
        findings.extend(self.check_worktrees())
        # 4. Ticket lifecycle checks
        findings.extend(self.check_ticket_lifecycle())
        # 5. Agent host checks
        findings.extend(self.check_agent_hosts())
        # 6. Local OneDev + Validator publication scope
        findings.extend(self.check_local_ci_publication())
        # 7. Session recovery & LLM agent storage integrity (via uncrash)
        findings.extend(self.check_session_recovery())
        # 8. Reuse standard checks if adopted or registered in standard-requirements.json
        registered_reqs: List[str] = []
        try:
            registered_reqs = self.validator.registered_requirements()
        except ValueError:
            pass
        reuse_required = "wellmanifest/reuse" in registered_reqs
        manifest_path = self.root / ".governance" / "manifest.json"
        if not reuse_required and manifest_path.is_file():
            try:
                mdata = json.loads(manifest_path.read_text(encoding="utf-8"))
                packs = mdata.get("packs", [])
                std_id = mdata.get("standard", {}).get("id", "")
                if "wellmanifest/reuse" in packs or std_id in ("wellmanifest/reuse", "profile:full"):
                    reuse_required = True
            except Exception:
                pass
        if reuse_required:
            findings.extend(self.check_reuse())
        # 9. Policy DSL and Lifecycle DSL validation and compaction audits when files exist
        findings.extend(self.check_policy_dsl())
        findings.extend(self.check_lifecycle_dsl())
        # 10. Additional registered standard checks
        if "wellmanifest/modularity" in registered_reqs:
            findings.extend(self.check_modularity())
        if "wellmanifest/priority" in registered_reqs:
            findings.extend(self.check_priority())
        if "wellmanifest/uriprocess" in registered_reqs:
            findings.extend(self.check_uriprocess())
        if "wellmanifest/mcp" in registered_reqs:
            findings.extend(self.check_mcp())
        if "wellmanifest/dockuri" in registered_reqs or (self.root / "dockuri.json").is_file() or (self.root / "dockuri.yaml").is_file():
            findings.extend(self.check_dockuri())
        if "wellmanifest/report" in registered_reqs:
            findings.extend(self.check_report())
        if "wellmanifest/hostguard" in registered_reqs:
            findings.extend(self.check_hostguard())
        return findings

    def check_local_ci_publication(self) -> List[Finding]:
        """Report the publication route scope; the unrestricted default needs no file."""
        from wellman.local_ci import POLICY_PATH, read_policy

        _policy, problem = read_policy(self.root)
        if problem is None:
            return []
        return [Finding(
            code="GOV-LOCAL-CI-001",
            message=f"Invalid {POLICY_PATH}: {problem}. The unrestricted local OneDev + Validator default applies.",
            severity="WARNING",
            path=str(POLICY_PATH),
            remediation=(
                'Fix it to {"schema": "new-project.local-ci-publication/v1", "scope": {"mode": "all"}} '
                "or a restricted OWNER/REPO allowlist, or delete it."
            ),
        )]

    def check_session_recovery(self, home: Optional[Path] = None) -> List[Finding]:
        """Validate wellmanifest/session-recovery standard compliance and agent storage health.

        Delegates to semcod/uncrash diagnostics when available to detect SQLite corruption,
        malformed conversation databases, and unhandled agent panics.
        """
        findings: List[Finding] = []
        target_home = (home or Path.home()).resolve()

        # Check adoption lock if repository adopts wellmanifest/session-recovery
        manifest_path = self.root / ".governance" / "manifest.json"
        if manifest_path.is_file():
            try:
                mdata = json.loads(manifest_path.read_text(encoding="utf-8"))
                packs = mdata.get("packs", [])
                if "wellmanifest/session-recovery" in packs:
                    lock_path = self.root / ".governance" / "session-recovery.lock.json"
                    if not lock_path.is_file():
                        findings.append(Finding(
                            code="GOV-SESSION-RECOVERY-LOCK",
                            message="Repository adopts 'wellmanifest/session-recovery' but is missing '.governance/session-recovery.lock.json'.",
                            severity="WARNING",
                            path=".governance/session-recovery.lock.json",
                            remediation="Run `wellman lock` or generate session-recovery adoption lockfile.",
                        ))
            except Exception:
                pass

        # Run storage health and panic detection via uncrash
        health_report = None
        try:
            from uncrash.diagnostics import check_agent_storage_health
            health_report = check_agent_storage_health(target_home)
        except ImportError:
            health_report = self._fallback_storage_health(target_home)

        if health_report:
            for corrupt in health_report.get("corrupted_sessions", []):
                findings.append(Finding(
                    code="GOV-SESSION-RECOVERY-001",
                    message=f"Corrupted LLM agent session storage detected in {corrupt.get('provider', 'agent')}: session '{corrupt.get('session_id')}' at {corrupt.get('path')}: {corrupt.get('error')}",
                    severity="ERROR",
                    path=corrupt.get("path", ""),
                    remediation=corrupt.get("remediation", "Run uncrash salvage or restore database from SQLite dump (INV-SR-002, INV-SR-003)."),
                ))
            for panic in health_report.get("detected_panics", []):
                findings.append(Finding(
                    code="GOV-SESSION-RECOVERY-002",
                    message=f"Detected unhandled agent panic in log '{panic.get('log_name', 'agent.log')}': {panic.get('signature', 'panic')}",
                    severity="WARNING",
                    path=panic.get("log_path", ""),
                    remediation="Review panic signature and verify crash isolation and session rehydration (INV-SR-001, INV-SR-005).",
                ))

        return findings

    def check_reuse(self) -> List[Finding]:
        """Validate wellmanifest/reuse standard compliance."""
        findings: List[Finding] = []

        # 1. Receipt verification
        receipt_path = self.root / ".reuse" / "redup-receipt.json"
        if not receipt_path.is_file():
            findings.append(Finding(
                code="GOV-REUSE-NO-RECEIPT",
                message="Missing .reuse/redup-receipt.json clone scan receipt.",
                severity="WARNING",
                path=".reuse/redup-receipt.json",
                remediation="Run `python3 scripts/record_scan_receipt.py` to record verified clone scan evidence.",
            ))
        else:
            try:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                findings_data = receipt.get("findings", {})
                if findings_data.get("unmitigated", 0) > 0:
                    findings.append(Finding(
                        code="GOV-REUSE-UNMITIGATED-CLONES",
                        message=f"Repository has {findings_data['unmitigated']} unmitigated clone group(s).",
                        severity="ERROR",
                        path=".reuse/redup-receipt.json",
                        remediation="Deduplicate shared logic or create an active tracking task in .planfile/sprints/.",
                    ))
            except Exception as e:
                findings.append(Finding(
                    code="GOV-REUSE-INVALID-RECEIPT",
                    message=f"Failed to parse .reuse/redup-receipt.json: {e}",
                    severity="ERROR",
                    path=".reuse/redup-receipt.json",
                    remediation="Re-run clone scan to generate a valid receipt.",
                ))

        # 2. Planfile / ticket tracking
        has_planfile = False
        sprints_dir = self.root / ".planfile" / "sprints"
        if sprints_dir.is_dir():
            has_planfile = any(sprints_dir.glob("*.yaml"))
        has_tickets = False
        proj_dir = self.root / "project"
        if proj_dir.is_dir():
            has_tickets = any(p.name.startswith("ticket-") for p in proj_dir.iterdir() if p.is_dir())

        if not has_planfile and not has_tickets:
            findings.append(Finding(
                code="GOV-REUSE-NO-PLANFILE",
                message="No active planfile sprint or project ticket found for reuse task tracking.",
                severity="WARNING",
                path=".planfile",
                remediation="Generate planfile tasks with `python3 scripts/generate_reuse_plan.py` or create a ticket.",
            ))

        # 3. Docs index
        docs_readme = self.root / "docs" / "README.md"
        if not docs_readme.is_file() or not docs_readme.read_text(encoding="utf-8").strip():
            findings.append(Finding(
                code="GOV-REUSE-NO-DOCS",
                message="Missing or empty docs/README.md documentation index.",
                severity="WARNING",
                path="docs/README.md",
                remediation="Create docs/README.md conforming to the Compact v2 documentation specification.",
            ))

        # 4. Optional stream-flow horizontal complexity audit (REUSE-015..018)
        stream_flow_cfg = self.root / ".reuse" / "stream-flow.json"
        if stream_flow_cfg.is_file():
            from wellman.stream_flow import analyze_horizontal_complexity
            report = analyze_horizontal_complexity(self.root)
            for hs in report.get("hotspots", []):
                findings.append(Finding(
                    code="GOV-REUSE-HORIZONTAL-HOTSPOT",
                    message=f"{hs['code']} in {hs['path']}:{hs['line']} (metric={hs['metric']}, limit={hs['limit']})",
                    severity="WARNING",
                    path=hs["path"],
                    remediation=hs["remediation"],
                ))

        return findings

    def check_modularity(self) -> List[Finding]:
        """Validate wellmanifest/modularity boundary contract when present."""
        findings: List[Finding] = []
        candidates = [
            self.root / "modularity.dsl",
            self.root / ".governance" / "modularity.dsl",
        ]
        doc_path = next((p for p in candidates if p.is_file()), None)
        if doc_path is None:
            return findings
        text = doc_path.read_text(encoding="utf-8")
        if "modularity " not in text and "module " not in text:
            findings.append(Finding(
                code="GOV-MODULARITY-INVALID",
                message=f"Modularity specification '{doc_path.relative_to(self.root)}' does not declare a modularity header or module block.",
                severity="ERROR",
                path=str(doc_path.relative_to(self.root)),
                remediation="Declare `modularity <id> version <semver>` and `module <name>` blocks per wellmanifest/modularity.",
            ))
        return findings

    def check_priority(self) -> List[Finding]:
        """Validate wellmanifest/priority ranking contract when present."""
        findings: List[Finding] = []
        candidates = [
            self.root / "priority.dsl",
            self.root / ".priority" / "priority.dsl",
            self.root / ".governance" / "priority.dsl",
        ]
        doc_path = next((p for p in candidates if p.is_file()), None)
        if doc_path is None:
            return findings
        text = doc_path.read_text(encoding="utf-8")
        if "priority_set " not in text and "priority " not in text:
            findings.append(Finding(
                code="GOV-PRIORITY-INVALID",
                message=f"Priority specification '{doc_path.relative_to(self.root)}' does not declare a priority_set or priority block.",
                severity="ERROR",
                path=str(doc_path.relative_to(self.root)),
                remediation="Declare `priority_set <id> version <semver>` and `priority <id> tier <tier>` blocks per wellmanifest/priority.",
            ))
        return findings

    def check_policy_dsl(self) -> List[Finding]:
        """Validate wellmanifest/policy-dsl .policy files and audit compaction via URI process."""
        from wellman.uri import uri

        findings: List[Finding] = []
        candidates: List[Path] = []
        for pattern in ("*.policy", "policies/*.policy", "profiles/**/*.policy", "examples/valid/*.policy", "examples/hosting/*.policy"):
            for p in sorted(self.root.glob(pattern)):
                if p.is_file() and p not in candidates:
                    candidates.append(p)

        for policy_path in candidates:
            rel_path = str(policy_path.relative_to(self.root))
            try:
                env = uri("proc://policy-dsl/audit", {"path": str(policy_path)})
                audit = env.get("result", {})
                for item in audit.get("findings", []):
                    findings.append(Finding(
                        code=item.get("code", "POLICY-COMPACT"),
                        message=item.get("message", "Policy compaction opportunity detected."),
                        severity="WARNING",
                        path=rel_path,
                        remediation=f"Refactor using {item.get('construct', 'compact Policy DSL constructs')}.",
                    ))
            except Exception as exc:
                findings.append(Finding(
                    code="GOV-POLICY-DSL-INVALID",
                    message=f"Invalid Policy DSL document '{rel_path}': {exc}",
                    severity="ERROR",
                    path=rel_path,
                    remediation="Fix syntax or semantic errors per wellmanifest/policy-dsl.",
                ))
        return findings

    def check_lifecycle_dsl(self) -> List[Finding]:
        """Validate wellmanifest/lifecycle .lifecycle files and audit compaction via URI process."""
        from wellman.uri import uri

        findings: List[Finding] = []
        candidates: List[Path] = []
        for pattern in ("*.lifecycle", "standard/*.lifecycle", "profiles/*.lifecycle", "subprojects/*/*.lifecycle"):
            for p in sorted(self.root.glob(pattern)):
                if p.is_file() and p not in candidates:
                    candidates.append(p)

        for lc_path in candidates:
            rel_path = str(lc_path.relative_to(self.root))
            try:
                uri("proc://lifecycle-dsl/validate", {"path": str(lc_path)})
                env = uri("proc://lifecycle-dsl/audit", {"path": str(lc_path)})
                audit = env.get("result", {})
                for item in audit.get("findings", []):
                    findings.append(Finding(
                        code=item.get("code", "LIFECYCLE-COMPACT"),
                        message=item.get("message", "Lifecycle compaction opportunity detected."),
                        severity="WARNING",
                        path=rel_path,
                        remediation=f"Refactor using {item.get('construct', 'compact Lifecycle DSL constructs')}.",
                    ))
            except Exception as exc:
                findings.append(Finding(
                    code="GOV-LIFECYCLE-DSL-INVALID",
                    message=f"Invalid Lifecycle DSL document '{rel_path}': {exc}",
                    severity="ERROR",
                    path=rel_path,
                    remediation="Fix state machine syntax or graph invariants per wellmanifest/lifecycle.",
                ))
        return findings

    def check_uriprocess(self) -> List[Finding]:
        """Validate wellmanifest/uriprocess package metadata and polyglot uri('') invocation links."""
        from wellman.uri import uri, validate_process_uri

        findings: List[Finding] = []
        pkg_manifest = self.root / "uriprocess.json"
        if pkg_manifest.is_file():
            try:
                data = json.loads(pkg_manifest.read_text(encoding="utf-8"))
                uris = list(data.get("public_uris", []))
                if "process_ref" in data:
                    uris.append(data["process_ref"])
                if not uris:
                    findings.append(Finding(
                        code="URP-SCHEMA-001",
                        message="uriprocess.json must declare 'public_uris' or 'process_ref'.",
                        severity="ERROR",
                        path="uriprocess.json",
                        remediation="Declare canonical process URIs in uriprocess.json.",
                    ))
                for u in uris:
                    validate_process_uri(str(u))
            except Exception as exc:
                findings.append(Finding(
                    code="URP-IDENTITY-001",
                    message=f"Invalid uriprocess.json: {exc}",
                    severity="ERROR",
                    path="uriprocess.json",
                    remediation="Ensure uriprocess.json conforms to wellmanifest/uriprocess.",
                ))

        scan_env = uri("proc://uriprocess/invocation/scan", {"root": str(self.root)})
        scan_res = scan_env.get("result", {})
        for item in scan_res.get("invalid_links", []):
            findings.append(Finding(
                code=item.get("code", "URP-IDENTITY-001"),
                message=f"{item.get('message')} at line {item.get('line')}",
                severity="ERROR",
                path=item.get("path", ""),
                remediation="Use canonical 'scheme://authority/path' process URI in uri('...') invocations.",
            ))
        return findings

    def check_logs(self) -> List[Finding]:
        """Validate wellmanifest/logs error catalog contract."""
        if not (self.root / "errors" / "README.md").is_file():
            return [Finding(
                code="GOV-LOGS-MISSING",
                message="wellmanifest/logs requires the error catalog errors/README.md.",
                severity="ERROR",
                path="errors/README.md",
                remediation="Add the consumer error catalog errors/README.md with one errors/{CODE}.md runbook per emitted code.",
            )]
        return []

    def check_mcp(self) -> List[Finding]:
        """Validate wellmanifest/mcp URI operation contract when present."""
        findings: List[Finding] = []
        mcp_candidates = (
            list(self.root.glob("**/mcp_server.py"))
            + list(self.root.glob("**/mcp.py"))
            + list(self.root.glob("src/**/mcp*.py"))
        )
        source_candidates = [
            p for p in mcp_candidates
            if p.is_file() and ".worktrees" not in p.parts and ".venv" not in p.parts and "tests" not in p.parts
        ]
        if not source_candidates:
            return [Finding(
                code="GOV-MCP-MISSING",
                message="Repository requires wellmanifest/mcp but no MCP server module (*mcp*.py) was found.",
                severity="ERROR",
                path=str(self.root),
                remediation="Implement an MCP server module exposing registry_search/task_plan/task_execute or MCP tools.",
            )]
        return findings

    def check_dockuri(self) -> List[Finding]:
        """Validate wellmanifest/dockuri manifest and cross-manifest URI parity (dockuri.json vs dockuri.yaml vs uriprocess.json)."""
        from wellman.uri import validate_process_uri

        findings: List[Finding] = []
        json_path = self.root / "dockuri.json"
        yaml_path = self.root / "dockuri.yaml"
        urp_path = self.root / "uriprocess.json"

        if not json_path.is_file() and not yaml_path.is_file():
            return [Finding(
                code="GOV-DOCKURI-MISSING",
                message="Repository requires wellmanifest/dockuri but neither dockuri.json nor dockuri.yaml exists.",
                severity="ERROR",
                path="dockuri.json",
                remediation="Create dockuri.json declaring project processes and canonical proc:// URIs.",
            )]

        json_uris: set[str] = set()
        json_version: Optional[str] = None
        if json_path.is_file():
            try:
                jdata = json.loads(json_path.read_text(encoding="utf-8"))
                json_version = jdata.get("project", {}).get("version") or jdata.get("version")
                for proc in jdata.get("processes", []):
                    if isinstance(proc, dict) and isinstance(proc.get("uri"), str):
                        validate_process_uri(proc["uri"])
                        json_uris.add(proc["uri"])
            except Exception as exc:
                findings.append(Finding(
                    code="GOV-DOCKURI-INVALID",
                    message=f"Invalid dockuri.json: {exc}",
                    severity="ERROR",
                    path="dockuri.json",
                    remediation="Ensure dockuri.json conforms to wellmanifest/dockuri.",
                ))

        if yaml_path.is_file():
            try:
                import yaml  # type: ignore

                ydata = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                if isinstance(ydata, dict):
                    yaml_uris = {
                        p["uri"]
                        for p in ydata.get("processes", [])
                        if isinstance(p, dict) and isinstance(p.get("uri"), str)
                    }
                    if json_uris and yaml_uris != json_uris:
                        diff = sorted(json_uris ^ yaml_uris)
                        findings.append(Finding(
                            code="GOV-DOCKURI-DRIFT",
                            message=(
                                f"SSoT URI drift between dockuri.json ({len(json_uris)} URIs) "
                                f"and dockuri.yaml ({len(yaml_uris)} URIs): {', '.join(diff)}"
                            ),
                            severity="ERROR",
                            path="dockuri.yaml",
                            remediation="Synchronize canonical process URIs between dockuri.json and dockuri.yaml.",
                        ))
            except ImportError:
                pass
            except Exception as exc:
                findings.append(Finding(
                    code="GOV-DOCKURI-INVALID",
                    message=f"Invalid dockuri.yaml: {exc}",
                    severity="ERROR",
                    path="dockuri.yaml",
                    remediation="Ensure dockuri.yaml is valid YAML and matches dockuri.json.",
                ))

        if urp_path.is_file() and json_uris:
            try:
                udata = json.loads(urp_path.read_text(encoding="utf-8"))
                urp_uris = set(udata.get("public_uris", []))
                if "process_ref" in udata and isinstance(udata["process_ref"], str):
                    urp_uris.add(udata["process_ref"])
                if urp_uris and urp_uris != json_uris:
                    diff = sorted(json_uris ^ urp_uris)
                    findings.append(Finding(
                        code="GOV-DOCKURI-URIPROCESS-DRIFT",
                        message=(
                            f"SSoT URI drift between dockuri.json ({len(json_uris)} URIs) "
                            f"and uriprocess.json ({len(urp_uris)} URIs): {', '.join(diff)}"
                        ),
                        severity="ERROR",
                        path="uriprocess.json",
                        remediation="Synchronize public_uris in uriprocess.json with dockuri.json processes.",
                    ))
                urp_version = udata.get("version")
                if json_version and urp_version and str(json_version) != str(urp_version):
                    findings.append(Finding(
                        code="GOV-DOCKURI-VERSION-DRIFT",
                        message=(
                            f"Version drift between dockuri.json ({json_version}) "
                            f"and uriprocess.json ({urp_version})."
                        ),
                        severity="ERROR",
                        path="uriprocess.json",
                        remediation="Synchronize package version across dockuri.json and uriprocess.json.",
                    ))
            except Exception:
                pass

        return findings

    def check_report(self) -> List[Finding]:
        """Validate wellmanifest/report contract when required."""
        if not (self.root / "docs").is_dir():
            return [Finding(
                code="GOV-REPORT-DOCS-MISSING",
                message="Repository requires wellmanifest/report but docs/ directory is missing.",
                severity="ERROR",
                path="docs",
                remediation="Create docs/ directory for reproducible reports and deliverables.",
            )]
        return []

    def check_hostguard(self) -> List[Finding]:
        """Validate wellmanifest/hostguard resource & storage guard contract when present."""
        findings: List[Finding] = []
        has_hostguard = (
            (self.root / "hostguard").is_dir()
            or (self.root / "schemas" / "hostguard.probe.v1.schema.json").is_file()
            or any(
                "hostguard" in p.read_text(encoding="utf-8", errors="ignore")
                for p in self.root.glob("**/*.py")
                if p.is_file() and ".worktrees" not in p.parts and ".venv" not in p.parts
            )
        )
        if not has_hostguard:
            findings.append(Finding(
                code="GOV-HOSTGUARD-MISSING",
                message="Repository requires wellmanifest/hostguard but no hostguard module or integration was found.",
                severity="ERROR",
                path=str(self.root),
                remediation="Integrate hostguard probe/storage resilience per wellmanifest/hostguard.",
            ))
        return findings

    def _fallback_storage_health(self, home: Path) -> dict:
        """Fallback lightweight scan for agent storage health when uncrash is uninstalled."""
        import sqlite3
        report: Dict[str, Any] = {"corrupted_sessions": [], "detected_panics": []}
        agy_root = home / ".gemini" / "antigravity-cli"
        if not agy_root.is_dir():
            return report

        # Check conversation databases
        conv_dir = agy_root / "conversations"
        if conv_dir.is_dir():
            for db_path in sorted(conv_dir.glob("*.db")):
                if not db_path.is_file():
                    continue
                try:
                    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=0.5)
                    try:
                        cur = conn.cursor()
                        cur.execute("PRAGMA quick_check;")
                        res = cur.fetchone()
                    finally:
                        conn.close()
                    if not res or res[0] != "ok":
                        report["corrupted_sessions"].append({
                            "provider": "agy",
                            "session_id": db_path.stem,
                            "path": str(db_path),
                            "error": res[0] if res else "quick_check failed",
                            "remediation": f"sqlite3 {db_path} .dump > dump.sql && sqlite3 restored.db < dump.sql",
                        })
                except sqlite3.OperationalError as e:
                    msg = str(e).lower()
                    if any(busy_marker in msg for busy_marker in ("locked", "busy", "unable to open database file", "resource temporarily unavailable")):
                        continue
                    report["corrupted_sessions"].append({
                        "provider": "agy",
                        "session_id": db_path.stem,
                        "path": str(db_path),
                        "error": str(e),
                        "remediation": f"sqlite3 {db_path} .dump > dump.sql && sqlite3 restored.db < dump.sql",
                    })
                except Exception as e:
                    report["corrupted_sessions"].append({
                        "provider": "agy",
                        "session_id": db_path.stem,
                        "path": str(db_path),
                        "error": str(e),
                        "remediation": f"sqlite3 {db_path} .dump > dump.sql && sqlite3 restored.db < dump.sql",
                    })

        # Check summary DB
        summary_db = agy_root / "conversation_summaries.db"
        if summary_db.is_file():
            try:
                conn = sqlite3.connect(f"file:{summary_db}?mode=ro", uri=True, timeout=0.5)
                try:
                    cur = conn.cursor()
                    cur.execute("PRAGMA quick_check;")
                    res = cur.fetchone()
                finally:
                    conn.close()
                if not res or res[0] != "ok":
                    report["corrupted_sessions"].append({
                        "provider": "agy",
                        "session_id": "conversation_summaries",
                        "path": str(summary_db),
                        "error": res[0] if res else "quick_check failed",
                        "remediation": "restore from SQLite dump or regenerate summaries",
                    })
            except sqlite3.OperationalError as e:
                msg = str(e).lower()
                if not any(busy_marker in msg for busy_marker in ("locked", "busy", "unable to open database file", "resource temporarily unavailable")):
                    report["corrupted_sessions"].append({
                        "provider": "agy",
                        "session_id": "conversation_summaries",
                        "path": str(summary_db),
                        "error": str(e),
                        "remediation": "restore from SQLite dump or regenerate summaries",
                    })
            except Exception as e:
                report["corrupted_sessions"].append({
                    "provider": "agy",
                    "session_id": "conversation_summaries",
                    "path": str(summary_db),
                    "error": str(e),
                    "remediation": "restore from SQLite dump or regenerate summaries",
                })

        # Scan recent logs for panics
        log_dir = agy_root / "log"
        if log_dir.is_dir():
            patterns = [
                re.compile(r"Caught panic:\s*(.*)", re.IGNORECASE),
                re.compile(r"runtime error:\s*(invalid memory address or nil pointer dereference.*)", re.IGNORECASE),
                re.compile(r"Failed to load conversation ([a-f0-9-]+):\s*(.*database disk image is malformed.*)", re.IGNORECASE),
                re.compile(r"program was killed:\s*(program experienced a panic.*)", re.IGNORECASE),
            ]
            for log_file in sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)[:20]:
                try:
                    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                        text = f.read(512 * 1024)
                    for pat in patterns:
                        m = pat.search(text)
                        if m:
                            report["detected_panics"].append({
                                "log_path": str(log_file),
                                "log_name": log_file.name,
                                "signature": m.group(0).strip(),
                            })
                            break
                except (OSError, UnicodeError):
                    continue

        return report

    def run_standard(self, standard_id: str) -> List[Finding]:
        """Run the concrete conformance check implemented for one standard.

        The registry is broader than the current executable checker set.  A
        selected standard must therefore fail closed when this release has no
        standard-specific check, rather than returning the result of an
        unrelated full scan.
        """
        checks = {
            "wellmanifest/new-project": self.validator.run_all_validations,
            "wellmanifest/git-lifecycle": self.check_git_lifecycle,
            "wellmanifest/worktrees": self.check_worktrees,
            "wellmanifest/ticket-lifecycle": self.check_ticket_lifecycle,
            "wellmanifest/merge": self.check_local_ci_publication,
            "wellmanifest/validation-attestation": self.check_local_ci_publication,
            "wellmanifest/agent": self.check_agent_hosts,
            "wellmanifest/docs": lambda: self.validator.validate_docs(required=True),
            "wellmanifest/logs": self.check_logs,
            "wellmanifest/session-recovery": self.check_session_recovery,
            "wellmanifest/reuse": self.check_reuse,
            "wellmanifest/modularity": self.check_modularity,
            "wellmanifest/priority": self.check_priority,
            "wellmanifest/policy-dsl": self.check_policy_dsl,
            "wellmanifest/lifecycle": self.check_lifecycle_dsl,
            "wellmanifest/legal-lifecycle": self.check_lifecycle_dsl,
            "wellmanifest/product-lifecycle": self.check_lifecycle_dsl,
            "wellmanifest/saas-lifecycle": self.check_lifecycle_dsl,
            "wellmanifest/twin-lifecycle": self.check_lifecycle_dsl,
            "wellmanifest/uriprocess": self.check_uriprocess,
            "wellmanifest/mcp": self.check_mcp,
            "wellmanifest/dockuri": self.check_dockuri,
            "wellmanifest/report": self.check_report,
            "wellmanifest/hostguard": self.check_hostguard,
        }
        check = checks.get(standard_id)
        if check is not None:
            return check()
        return [Finding(
            code="GOV-STANDARD-NOT-IMPLEMENTED",
            message=(
                f"No standard-specific conformance check is implemented for "
                f"'{standard_id}'."
            ),
            remediation="Run `wellman check` for the available aggregate checks or implement this standard's checker.",
        )]

    def run_canonical_gate(self, extra_args: Optional[List[str]] = None) -> int:
        """Run the verified adopted gate, falling back only without adoption."""
        from wellman.adoption import safe_path

        try:
            safe_path(self.requested_root)
        except (OSError, ValueError) as error:
            print(f"ERROR: Cannot establish the requested check context: {error}", file=sys.stderr)
            return 1
        admission = _worktree_admission(self.root)
        if admission is not None:
            print(f"ERROR: {admission}", file=sys.stderr)
            return 1
        try:
            checker = _adopted_checker(self.root, ".governance/governance_check.py")
        except (OSError, ValueError, TypeError):
            print("ERROR: Cannot verify the adopted governance checker and its pinned dependencies.", file=sys.stderr)
            return 1
        if not checker:
            print("ERROR: Canonical governance_check.py script not found.", file=sys.stderr)
            return 1

        cmd = [sys.executable, str(checker), "--root", str(self.root)]
        if extra_args:
            cmd.extend(extra_args)

        try:
            res = subprocess.run(cmd, cwd=str(self.root), env=_git_environment())
        except (OSError, subprocess.SubprocessError):
            print("ERROR: The required governance checker could not execute.", file=sys.stderr)
            return 1
        return res.returncode
