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


class ConformanceRunner:
    """Runs conformance checks across all adopted standards."""

    def __init__(self, root: Path):
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
        findings: List[Finding] = []
        worktrees_dir = self.root / ".worktrees"

        # Check bundled worktree overlap check if available
        checker = _find_bundled_script("worktree_overlap_check.py")
        if checker and (self.root / ".git").exists():
            try:
                res = subprocess.run(
                    [sys.executable, str(checker), "--root", str(self.root)],
                    cwd=str(self.root),
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if res.returncode != 0:
                    for line in res.stdout.splitlines() + res.stderr.splitlines():
                        if "OVERLAP" in line or "ERROR" in line:
                            findings.append(Finding(
                                code="GOV-WORKTREE-OVERLAP-001",
                                message=line.strip(),
                                severity="ERROR",
                                remediation="Resolve concurrent file changes across worktrees or unbind overlapping paths.",
                            ))
            except Exception:
                pass

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
        # 8. Reuse standard checks if adopted
        manifest_path = self.root / ".governance" / "manifest.json"
        if manifest_path.is_file():
            try:
                mdata = json.loads(manifest_path.read_text(encoding="utf-8"))
                packs = mdata.get("packs", [])
                std_id = mdata.get("standard", {}).get("id", "")
                if "wellmanifest/reuse" in packs or std_id in ("wellmanifest/reuse", "profile:full"):
                    findings.extend(self.check_reuse())
            except Exception:
                pass
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
            "wellmanifest/agent": self.check_agent_hosts,
            "wellmanifest/docs": lambda: self.validator.validate_docs(required=True),
            "wellmanifest/session-recovery": self.check_session_recovery,
            "wellmanifest/reuse": self.check_reuse,
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
        """Run the bundled canonical governance_check.py gate."""
        checker = _find_bundled_script("governance_check.py")
        if not checker:
            print("ERROR: Canonical governance_check.py script not found.", file=sys.stderr)
            return 1

        cmd = [sys.executable, str(checker), "--root", str(self.root)]
        if extra_args:
            cmd.extend(extra_args)

        res = subprocess.run(cmd, cwd=str(self.root))
        return res.returncode
