"""Wellman Command-Line Interface.

Unified CLI for managing, validating, and enforcing all Wellmanifest standards.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

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

    selected_standard = get_standard(args.standard) if args.standard else None
    if args.standard and selected_standard is None:
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
    print("✓ Adoption scaffolded. Requirements registered, not verified. Run `wellman check` and resolve remaining findings before treating it as conformant.")
    return 0


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
    p_adopt.add_argument("--force", action="store_true", help="Replace an existing adoption manifest")
    p_adopt.add_argument('--profile', action='append', default=[], help='Additional capability profile for auto registration')
    p_adopt.add_argument('--dry-run', action='store_true', help='Preview auto registration without writes')
    p_adopt.add_argument('--json', action='store_true', help='Return auto registration as JSON')
    p_adopt.set_defaults(func=cmd_adopt)

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
