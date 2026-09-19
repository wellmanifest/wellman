"""Standard Conformance Runner.

Executes deterministic checks across all Wellmanifest standards:
- Git lifecycle (branches, commit scope, intent)
- Worktrees (naming, placement, overlap detection)
- Ticket lifecycle (intent, activity, allocations)
- Agent & host contracts (AGENTS.md, host bindings)
- Canonical governance gate delegation
"""

from __future__ import annotations

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
                    ticket_pattern = re.compile(r"^(ticket/\d+|feature/|fix/|chore/|release/|governance/)")
                    if not ticket_pattern.match(branch):
                        findings.append(Finding(
                            code="GOV-GIT-001",
                            message=f"Branch '{branch}' does not conform to Wellmanifest git-lifecycle naming.",
                            severity="WARNING",
                            path=f"branch:{branch}",
                            remediation="Use conventional branch prefix: ticket/NNN-*, feature/*, fix/*, chore/*, or release/*.",
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
        return findings

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
