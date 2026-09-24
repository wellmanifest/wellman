"""Wellman Command-Line Interface.

Unified CLI for managing, validating, and enforcing all Wellmanifest standards.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Set

from wellman import __version__
from wellman.registry import (
    CONFORMANCE_LEVELS,
    PROFILES_CATALOG,
    STANDARDS_CATALOG,
    get_profile,
    get_standard,
    list_profiles,
    list_standards,
)
from wellman.runner import ConformanceRunner
from wellman.validator import Finding, StandardsValidator, load_bundled_schema, validate_json_structure
from wellman.docs_adoption import render_adoption
from wellman.fleet import (
    apply_plan,
    build_plan,
    check_fleet,
    discover_repositories,
    emit_standardization_tickets,
    feed_to_planfile,
    sync_fleet_agents,
)
from wellman.repository import RepositoryIdentityError


_CANONICAL_WORKTREE = re.compile(
    r"^ticket-(?P<number>[0-9]{3,})--(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)$"
)
_CANONICAL_BRANCH = re.compile(
    r"^refs/heads/ticket-(?P<number>[0-9]{3,})-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)$"
)


def _git_worktree_records(root: Path) -> list[dict[str, str]]:
    """Read Git's registered worktrees without repairing or mutating them."""
    result = subprocess.run(
        ["git", "-C", str(root), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
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


def _worktree_admission(root: Path) -> Optional[Finding]:
    """Reject execution from an unregistered or system-temporary checkout.

    A plain clone is a valid Git repository from Git's perspective, so Git
    alone cannot distinguish it from the adopter's primary checkout. The
    explicit system-temp rejection closes the failure mode that caused agents
    to work from ``/tmp``; linked delivery worktrees additionally require the
    v5 directory/branch identity.
    """
    if not (root / ".git").exists():
        return None

    try:
        top_level = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if top_level.returncode != 0:
            raise ValueError("Git checkout is not readable")
        observed_root = Path(top_level.stdout.strip()).resolve()
        if observed_root != root:
            raise ValueError("requested root is not the Git checkout root")

        try:
            root.relative_to(Path("/tmp"))
        except ValueError:
            pass
        else:
            return Finding(
                code="GOV-WORKTREE-ADMISSION-001",
                message="Refusing to run from a Git checkout below /tmp.",
                path=str(root),
                remediation=(
                    "Use the registered primary checkout or create "
                    "<primary>/.worktrees/ticket-NNN--slug through the allocator."
                ),
            )

        records = _git_worktree_records(root)
        canonical_root = next(
            (Path(record["path"]).resolve() for record in records
             if Path(record["path"]).resolve() == root),
            None,
        )
        if canonical_root is None:
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


def print_banner() -> None:
    print(f"wellman v{__version__} — Wellmanifest Unified Standards Runtime")


def cmd_version(args: argparse.Namespace) -> int:
    print(f"wellman {__version__}")
    print(f"Standards suite: wellmanifest 0.20.x")
    print(f"Registered standards: {len(STANDARDS_CATALOG)}")
    print(f"Registered profiles: {len(PROFILES_CATALOG)}")
    return 0


def cmd_standards(args: argparse.Namespace) -> int:
    standards = list_standards()

    if args.json:
        out = [s.to_dict() for s in standards]
        print(json.dumps(out, indent=2))
        return 0

    print_banner()
    print(f"\nSupported Wellmanifest Standards ({len(standards)} registered):\n")
    fmt = "{:<32} {:<6} {:<24} {:<40}"
    print(fmt.format("STANDARD ID", "LEVEL", "EXECUTION MODEL", "NAME"))
    print("-" * 105)

    for std in sorted(standards, key=lambda s: s.id):
        print(fmt.format(std.id, std.minimum_level, std.execution_model, std.name[:38]))

    print("\nRun `wellman info <standard-id>` for detailed specification and schemas.")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    std = get_standard(args.standard_id)
    if not std:
        print(f"Error: Unknown standard '{args.standard_id}'.", file=sys.stderr)
        print("Run `wellman standards` to view available standards.", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(std.to_dict(), indent=2))
        return 0

    print_banner()
    print(f"\nStandard: {std.name} ({std.id})")
    print("=" * 60)
    print(f"Owner:           {std.owner}")
    print(f"Description:     {std.description}")
    print(f"Minimum Level:   {std.minimum_level} ({CONFORMANCE_LEVELS.get(std.minimum_level, '')})")
    print(f"Execution Model: {std.execution_model}")
    print(f"Documentation:   {std.docs_url or 'N/A'}")

    if std.owns:
        print("\nOwned Concerns:")
        for own in std.owns:
            print(f"  ✓ {own}")

    if std.excludes:
        print("\nExcluded Concerns:")
        for exc in std.excludes:
            print(f"  ✗ {exc}")

    if std.schemas:
        print("\nAssociated Schemas:")
        for schema in std.schemas:
            print(f"  • {schema}")

    return 0


def cmd_profiles(args: argparse.Namespace) -> int:
    profiles = list_profiles()

    if args.json:
        out = [p.to_dict() for p in profiles]
        print(json.dumps(out, indent=2))
        return 0

    print_banner()
    print(f"\nWellmanifest Adoption Profiles:\n")

    for p in profiles:
        print(f"Profile: {p.name}")
        print(f"  Description: {p.description}")
        if p.extends:
            print(f"  Extends:     {', '.join(p.extends)}")
        print("  Requirements:")
        for req in p.requirements:
            print(f"    - {req.get('id')} ({req.get('minimumLevel')})")
        print()

    return 0


def cmd_check(args: argparse.Namespace) -> int:
    root = Path(args.root or ".").resolve()
    runner = ConformanceRunner(root)

    admission = _worktree_admission(root)
    selected_standard = get_standard(args.standard) if args.standard else None
    if admission is not None:
        findings = [admission]
    elif args.standard and selected_standard is None:
        findings = [
            Finding(
                code="GOV-STANDARD-UNKNOWN",
                message=f"Unknown standard '{args.standard}'.",
                remediation="Run `wellman standards` to view registered standards.",
            )
        ]
    elif selected_standard is not None:
        findings = runner.run_standard(selected_standard.id)
    else:
        findings = runner.run_all()
    errors = [f for f in findings if f.severity == "ERROR"]
    warnings = [f for f in findings if f.severity == "WARNING"]

    if args.json:
        out = {
            "root": str(root),
            "valid": len(errors) == 0,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "findings": [f.to_dict() for f in findings],
        }
        print(json.dumps(out, indent=2))
        return 0 if not errors else 1

    print_banner()
    print(f"\nChecking standards compliance in: {root}")
    print("-" * 60)

    if not findings:
        print("✓ All Wellmanifest standard conformance checks passed!")
        return 0

    for f in findings:
        color_prefix = "❌" if f.severity == "ERROR" else "⚠️ "
        print(f"{color_prefix} {f}")
        if f.remediation:
            print(f"   Remediation: {f.remediation}")

    print(f"\nSummary: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


def cmd_gate(args: argparse.Namespace) -> int:
    """Run canonical deterministic governance gate."""
    root = Path(args.root or ".").resolve()
    admission = _worktree_admission(root)
    if admission is not None:
        print(f"❌ {admission}", file=sys.stderr)
        if admission.remediation:
            print(f"   Remediation: {admission.remediation}", file=sys.stderr)
        return 1
    runner = ConformanceRunner(root)
    extra_args = []
    if args.preflight:
        extra_args.append("--preflight")
    if args.workstream:
        extra_args.extend(["--workstream", args.workstream])
    if args.ticket:
        extra_args.extend(["--ticket", args.ticket])
    return runner.run_canonical_gate(extra_args)


def cmd_validate(args: argparse.Namespace) -> int:
    target_file = Path(args.file).resolve()
    if not target_file.is_file():
        print(f"Error: File '{target_file}' not found.", file=sys.stderr)
        return 1

    schema_name = args.schema
    if not schema_name:
        # Infer schema from filename
        schema_name = target_file.name.replace(".json", "")

    schema = load_bundled_schema(schema_name)
    if not schema:
        print(f"Error: Schema '{schema_name}' not found in bundled schemas.", file=sys.stderr)
        return 1

    try:
        data = json.loads(target_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error reading JSON from '{target_file}': {e}", file=sys.stderr)
        return 1

    findings = validate_json_structure(data, schema)
    if findings:
        print(f"❌ Validation failed for {target_file.name} against schema {schema_name}:")
        for f in findings:
            print(f"  • {f}")
        return 1

    print(f"✓ {target_file.name} is valid against schema {schema_name}.")
    return 0


def cmd_adopt(args: argparse.Namespace) -> int:
    from wellman.adoption import register, repository_root, safe_path
    try:
        root = repository_root(args.root or '.', bootstrap=args.bootstrap)
        for name in ('manifest.json', 'standard-packs.json', 'standard-requirements.json'):
            safe_path(root / '.governance' / name)
    except (OSError, ValueError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    if args.standard_id == 'auto':
        try:
            if args.force:
                raise ValueError('--force is not supported by additive auto registration')
            result = register(root, args.profile, dry_run=args.dry_run)
        except (OSError, ValueError, UnicodeError) as error:
            print(f'Error: {error}', file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            action = 'Would register' if args.dry_run else 'Registered'
            print(f"{action} {len(result['registration']['requirements'])} required standards: {result['path']}")
            print('Requirements only: adoption pins, conformance and protected enforcement remain unverified.')
        return 0
    if args.dry_run or args.profile or args.json:
        print('Error: --dry-run, --profile and --json require adopt auto.', file=sys.stderr)
        return 1
    std = get_standard(args.standard_id)
    profile = get_profile(args.standard_id)

    gov_dir = root / ".governance"
    manifest_path = gov_dir / "manifest.json"
    if std is None and profile is None:
        print(f"Error: Unknown standard or profile '{args.standard_id}'.", file=sys.stderr)
        print("Run `wellman standards` or `wellman profiles` to view supported values.", file=sys.stderr)
        return 1
    if manifest_path.exists() and not args.force:
        print(
            f"Error: {manifest_path} already exists; refusing to overwrite it without --force.",
            file=sys.stderr,
        )
        return 1

    selected_profiles = [profile.name] if profile else []
    selected_standards = [std.id] if std else []
    try:
        # Validate the registration before the legacy scaffold writes anything.
        register(root, selected_profiles, standards=selected_standards, dry_run=True)
    except (OSError, ValueError, UnicodeError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1

    def profile_includes(profile_name: str, target: str, seen: Optional[Set[str]] = None) -> bool:
        seen = seen or set()
        if profile_name in seen:
            return False
        seen.add(profile_name)
        current = get_profile(profile_name)
        if current is None:
            return False
        if any(item.get("id") == target for item in current.requirements):
            return True
        return any(profile_includes(parent, target, seen) for parent in current.extends)

    adopts_docs = bool(std and std.id == "wellmanifest/docs") or bool(
        profile and profile_includes(profile.name, "wellmanifest/docs")
    )
    docs_content = None
    if adopts_docs:
        try:
            docs_content = render_adoption(root, args.repository)
        except RepositoryIdentityError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    if docs_content is not None:
        docs_path = gov_dir / "docs.json"
        if docs_path.exists() and not args.force:
            try:
                existing = docs_path.read_text(encoding="utf-8")
            except OSError as exc:
                print(f"Error: cannot read {docs_path}: {exc}", file=sys.stderr)
                return 1
            if existing != docs_content:
                print(
                    f"Error: {docs_path} already contains a different repository binding; "
                    "use --force only after reviewing it.",
                    file=sys.stderr,
                )
                return 1

    gov_dir.mkdir(parents=True, exist_ok=True)
    print(f"Adopting '{args.standard_id}' into {root}...")
    manifest_data = {
        "schema": "wellmanifest.manifest/v1",
        "standard": {
            "id": std.id if std else (f"profile:{profile.name}" if profile else args.standard_id),
            "version": __version__,
        },
    }
    manifest_path.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")
    print(f"✓ Created {manifest_path.relative_to(root)}")

    # Copy standard-packs.json
    bundled_packs = Path(__file__).parent / "schemas" / "standard-packs.json"
    if bundled_packs.is_file():
        target_packs = gov_dir / "standard-packs.json"
        if not target_packs.exists():
            target_packs.write_text(bundled_packs.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"✓ Attached {target_packs.relative_to(root)}")

    try:
        register(root, selected_profiles, standards=selected_standards)
    except (OSError, ValueError, UnicodeError) as error:
        print(f'Error: scaffold created but requirement registration failed: {error}', file=sys.stderr)
        return 1

    if docs_content is not None:
        docs_path = gov_dir / "docs.json"
        if not docs_path.exists() or args.force:
            docs_path.write_text(docs_content, encoding="utf-8")
            print(f"✓ Created {docs_path.relative_to(root)}")

    print("✓ Adoption scaffolded. Requirements registered, not verified. Run `wellman check` and resolve remaining findings before treating it as conformant.")
    return 0


def _print_fleet_payload(payload: object, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    if isinstance(payload, dict) and "repositories" in payload:
        repositories = payload["repositories"]
        for item in repositories:
            if isinstance(item, dict):
                status = "READY" if item.get("ready", item.get("valid", False)) else "BLOCKED"
                if "status" in item:
                    status = str(item["status"]).upper()
                print(f"{status}: {item.get('path', '<unknown>')}")
                for action in item.get("actions", []):
                    print(f"  action: {action}")
                for blocker in item.get("blockers", []):
                    print(f"  blocker: {blocker}")
                for finding in item.get("findings", []):
                    print(f"  finding: {finding.get('code', 'UNKNOWN')}: {finding.get('message', '')}")
        if "ready" in payload or "blocked" in payload:
            print(f"ready={payload.get('ready', 0)} blocked={payload.get('blocked', 0)}")
        elif "valid" in payload:
            print(f"valid={payload['valid']} repositories={len(repositories)}")
        return
    for item in payload if isinstance(payload, list) else []:
        print(item)


def cmd_fleet_discover(args: argparse.Namespace) -> int:
    repositories = discover_repositories(Path(args.root), args.recursive)
    payload = {"root": str(Path(args.root).resolve()), "repositories": [str(path) for path in repositories]}
    _print_fleet_payload(payload, args.json)
    return 0


def cmd_fleet_sync_agents(args: argparse.Namespace) -> int:
    payload = sync_fleet_agents(Path(args.root), args.recursive)
    _print_fleet_payload(payload, args.json)
    return 0


def cmd_fleet_plan(args: argparse.Namespace) -> int:
    try:
        payload = build_plan(
            Path(args.root), args.target, args.recursive, args.allow_dirty, args.update_manifests
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    _print_fleet_payload(payload, args.json)
    return 0 if payload["blocked"] == 0 else 2


def cmd_fleet_adopt(args: argparse.Namespace) -> int:
    try:
        plan = build_plan(
            Path(args.root), args.target, args.recursive, args.allow_dirty, args.update_manifests
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not args.apply:
        _print_fleet_payload(plan, args.json)
        print("dry-run only; pass --apply to write changes", file=sys.stderr)
        return 0 if plan["blocked"] == 0 else 2
    payload = apply_plan(plan, args.target, args.update_manifests)
    _print_fleet_payload(payload, args.json)
    return 0 if plan["blocked"] == 0 and all(
        item.get("status") == "updated" for item in payload["repositories"]
    ) else 2


def cmd_fleet_check(args: argparse.Namespace) -> int:
    payload = check_fleet(Path(args.root), args.recursive)
    _print_fleet_payload(payload, args.json)

    emit_planfile = getattr(args, "emit_planfile", None)
    feed_planfile_arg = getattr(args, "feed_planfile", None)
    koru_handoff = getattr(args, "koru_handoff", False)
    monag_triage = getattr(args, "monag_triage", False)

    if emit_planfile or feed_planfile_arg is not None or koru_handoff:
        tickets_doc = emit_standardization_tickets(
            payload,
            koru_ready=koru_handoff,
            monag_triage=monag_triage,
        )
        if emit_planfile:
            target_path = Path(emit_planfile)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(json.dumps(tickets_doc, indent=2) + "\n", encoding="utf-8")
            if not args.json:
                print(f"Emitted {tickets_doc.get('count', 0)} standardization tickets to {target_path}")

        if feed_planfile_arg is not None:
            project_dir = Path(feed_planfile_arg) if feed_planfile_arg else None
            feed_result = feed_to_planfile(tickets_doc, project_dir)
            if not args.json:
                if feed_result.get("ok"):
                    print(f"Fed {feed_result.get('count', 0)} tickets to Planfile")
                else:
                    print(f"Failed to feed Planfile: {feed_result.get('error')}", file=sys.stderr)

    return 0 if payload["valid"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wellman",
        description="Wellman — Wellmanifest Unified Standards Runtime & Governance CLI",
    )
    parser.add_argument("--version", "-v", action="store_true", help="Show version information")
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # check
    p_check = subparsers.add_parser("check", help="Check standards compliance")
    p_check.add_argument("--root", "-r", default=".", help="Target repository root path")
    p_check.add_argument("--standard", "-s", help="Check compliance for a specific standard id")
    p_check.add_argument("--json", action="store_true", help="Output findings as JSON")
    p_check.set_defaults(func=cmd_check)

    # standards / list
    p_std = subparsers.add_parser("standards", help="List all supported Wellmanifest standards")
    p_std.add_argument("--json", action="store_true", help="Output list as JSON")
    p_std.set_defaults(func=cmd_standards)

    p_list = subparsers.add_parser("list", help="Alias for 'standards'")
    p_list.add_argument("--json", action="store_true", help="Output list as JSON")
    p_list.set_defaults(func=cmd_standards)

    # info
    p_info = subparsers.add_parser("info", help="Show detailed info about a specific standard")
    p_info.add_argument("standard_id", help="Standard ID (e.g. wellmanifest/git-lifecycle)")
    p_info.add_argument("--json", action="store_true", help="Output info as JSON")
    p_info.set_defaults(func=cmd_info)

    # profiles
    p_prof = subparsers.add_parser("profiles", help="List Wellmanifest governance profiles")
    p_prof.add_argument("--json", action="store_true", help="Output profiles as JSON")
    p_prof.set_defaults(func=cmd_profiles)

    # validate
    p_val = subparsers.add_parser("validate", help="Validate a JSON file against standard schemas")
    p_val.add_argument("file", help="Path to JSON file to validate")
    p_val.add_argument("--schema", "-s", help="Schema name (e.g. manifest, worktrees, intent)")
    p_val.set_defaults(func=cmd_validate)

    # adopt
    p_adopt = subparsers.add_parser("adopt", help="Adopt standard or profile into repository")
    p_adopt.add_argument("standard_id", nargs='?', default='auto', help="Standard ID, profile, or auto (default)")
    p_adopt.add_argument("--root", "-r", default=".", help="Target repository root path")
    p_adopt.add_argument('--bootstrap', action='store_true', help='Explicitly allow adoption into a non-Git directory; Git targets still resolve to their checkout root')
    p_adopt.add_argument("--repository", help="Canonical GitHub owner/name when origin is unavailable")
    p_adopt.add_argument("--force", action="store_true", help="Replace an existing adoption manifest")
    p_adopt.add_argument('--profile', action='append', default=[], help='Additional capability profile for auto registration')
    p_adopt.add_argument('--dry-run', action='store_true', help='Preview auto registration without writes')
    p_adopt.add_argument('--json', action='store_true', help='Return auto registration as JSON')
    p_adopt.set_defaults(func=cmd_adopt)

    # fleet
    p_fleet = subparsers.add_parser("fleet", help="Discover, plan and check a repository fleet")
    fleet_commands = p_fleet.add_subparsers(dest="fleet_command", required=True)

    p_fleet_discover = fleet_commands.add_parser("discover", help="List repositories below a directory")
    p_fleet_discover.add_argument("--root", "-r", default=".")
    p_fleet_discover.add_argument("--recursive", dest="recursive", action="store_true", default=None, help="Force recursive repository search")
    p_fleet_discover.add_argument("--no-recursive", dest="recursive", action="store_false", help="Disable recursive search")
    p_fleet_discover.add_argument("--json", action="store_true")
    p_fleet_discover.set_defaults(func=cmd_fleet_discover)

    p_fleet_sync = fleet_commands.add_parser("sync-agents", help="Project and sync agent instructions across repositories")
    p_fleet_sync.add_argument("--root", "-r", default=".")
    p_fleet_sync.add_argument("--recursive", dest="recursive", action="store_true", default=None, help="Force recursive repository search")
    p_fleet_sync.add_argument("--no-recursive", dest="recursive", action="store_false", help="Disable recursive search")
    p_fleet_sync.add_argument("--json", action="store_true")
    p_fleet_sync.set_defaults(func=cmd_fleet_sync_agents)

    for command, handler, help_text in (
        ("plan", cmd_fleet_plan, "Create a read-only fleet adoption plan"),
        ("adopt", cmd_fleet_adopt, "Apply a fleet adoption plan"),
    ):
        fleet_parser = fleet_commands.add_parser(command, help=help_text)
        fleet_parser.add_argument("target", help="Standard ID or profile name, e.g. baseline")
        fleet_parser.add_argument("--root", "-r", default=".")
        fleet_parser.add_argument("--recursive", dest="recursive", action="store_true", default=None, help="Force recursive repository search")
        fleet_parser.add_argument("--no-recursive", dest="recursive", action="store_false", help="Disable recursive search")
        fleet_parser.add_argument("--allow-dirty", action="store_true", help="Allow writes to dirty repositories")
        fleet_parser.add_argument("--update-manifests", action="store_true", help="Update only wellman-owned manifest version fields")
        fleet_parser.add_argument("--json", action="store_true")
        if command == "adopt":
            fleet_parser.add_argument("--apply", action="store_true", help="Actually write the planned changes")
        fleet_parser.set_defaults(func=handler)

    p_fleet_check = fleet_commands.add_parser("check", help="Run wellman checks across repositories")
    p_fleet_check.add_argument("--root", "-r", default=".")
    p_fleet_check.add_argument("--recursive", dest="recursive", action="store_true", default=None, help="Force recursive repository search")
    p_fleet_check.add_argument("--no-recursive", dest="recursive", action="store_false", help="Disable recursive search")
    p_fleet_check.add_argument("--json", action="store_true")
    p_fleet_check.add_argument("--emit-planfile", help="Export compliance findings as Planfile tickets JSON")
    p_fleet_check.add_argument("--koru-handoff", action="store_true", help="Add koru refactor executor and remediation intent metadata")
    p_fleet_check.add_argument("--feed-planfile", nargs="?", const="", help="Feed tickets directly to Planfile backlog")
    p_fleet_check.add_argument("--monag-triage", action="store_true", help="Cross-check scope conflicts via monag if installed")
    p_fleet_check.set_defaults(func=cmd_fleet_check)

    # gate
    p_gate = subparsers.add_parser("gate", help="Run deterministic governance gate")
    p_gate.add_argument("--root", "-r", default=".", help="Target repository root path")
    p_gate.add_argument("--preflight", action="store_true", help="Fast local preflight check")
    p_gate.add_argument("--workstream", help="Active workstream ID")
    p_gate.add_argument("--ticket", help="Active ticket ID")
    p_gate.set_defaults(func=cmd_gate)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version or args.command == "version":
        return cmd_version(args)

    if hasattr(args, "func"):
        return args.func(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
