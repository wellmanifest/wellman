#!/usr/bin/env python3
"""Adopt an immutable new-project governance revision into a target repository."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

PACKAGE_MANIFEST = "governance/package-manifest.json"
MANIFEST_SOURCE = "governance/manifest.default.json"
MANIFEST_BASE_TARGET = ".governance/manifest.base.json"
MANIFEST_TARGET = ".governance/manifest.json"
# ticket-206: the adopter seed is a template. Before it, this source was the
# hub's own live instance, so every unadapted adopter declared
# wellmanifest/new-project and required the hub's job names. The previous
# source stays accepted so a repository pinned before the change still
# generates a valid lock while it upgrades.
UNRESOLVED_ADOPTER = "unresolved/adopter"
CHECKS_SOURCE = "template/files/required-checks.template.json"
CHECKS_SOURCE_LEGACY = "governance/required-checks.json"
CHECKS_TARGET = ".governance/required-checks.json"
TICKET_ALLOCATION_SOURCE = "governance/ticket-allocation.json"
TICKET_ALLOCATION_TARGET = ".governance/ticket-allocation.json"
ALLOWED_EXTENDABLE = {
    (MANIFEST_SOURCE, MANIFEST_TARGET),
    (CHECKS_SOURCE, CHECKS_TARGET),
    (CHECKS_SOURCE_LEGACY, CHECKS_TARGET),
    (TICKET_ALLOCATION_SOURCE, TICKET_ALLOCATION_TARGET),
}
TARGET_OWNED_MANIFEST_PATHS = {
    ("$schema",),
    ("docker", "required"),
    ("coordination", "workstreams"),
    ("coordination", "integration", "requiredForPaths"),
    ("delivery", "requiredForImplementation"),
    ("delivery", "publicInterfacePaths"),
}
CANONICAL_STANDARD_REPOSITORY = "https://github.com/wellmanifest/new-project.git"
CANONICAL_STANDARD_RELEASES_API = (
    "https://api.github.com/repos/wellmanifest/new-project/releases/tags"
)
MAX_RELEASE_METADATA_BYTES = 1024 * 1024
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")


def git_bytes(root: Path, revision: str, source: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{revision}:{source}"], cwd=root)


def canonical_tag_revision(version: str) -> str:
    """Resolve one annotated canonical tag without trusting local Git refs."""
    tag = f"v{version}"
    result = subprocess.run(
        [
            "git",
            "ls-remote",
            "--tags",
            CANONICAL_STANDARD_REPOSITORY,
            f"refs/tags/{tag}",
            f"refs/tags/{tag}^{{}}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"the canonical standard tag {tag} could not be verified")
    refs: dict[str, str] = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 2 or re.fullmatch(r"[0-9a-f]{40}", fields[0]) is None:
            raise SystemExit(f"the canonical standard tag {tag} returned invalid Git evidence")
        if fields[1] in refs:
            raise SystemExit(f"the canonical standard tag {tag} returned duplicate Git evidence")
        refs[fields[1]] = fields[0]
    direct_ref = f"refs/tags/{tag}"
    peeled_ref = f"refs/tags/{tag}^{{}}"
    if direct_ref not in refs:
        raise SystemExit(f"the requested standard revision has no published release tag {tag}")
    if peeled_ref not in refs or refs[peeled_ref] == refs[direct_ref]:
        raise SystemExit(f"the standard release tag {tag} must be an annotated Git tag")
    return refs[peeled_ref]


def canonical_release(version: str) -> dict[str, object]:
    """Read bounded, final GitHub Release metadata for the standard version."""
    tag = f"v{version}"
    credential = os.environ.get("GH" + "_" + "TOKEN") or os.environ.get("GITHUB" + "_" + "TOKEN")
    if not credential:
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            candidate = result.stdout.strip()
            if result.returncode == 0 and candidate:
                credential = candidate
        except (OSError, subprocess.SubprocessError):
            pass
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "new-project-adoption-generator",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if credential:
        headers["Authorization"] = f"Bearer {credential}"
    request = Request(
        f"{CANONICAL_STANDARD_RELEASES_API}/{quote(tag, safe='')}",
        headers=headers,
    )
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read(MAX_RELEASE_METADATA_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise SystemExit(
            f"the canonical standard has no verifiable published GitHub Release {tag}"
        ) from error
    if len(raw) > MAX_RELEASE_METADATA_BYTES:
        raise SystemExit(
            f"the canonical GitHub Release metadata for {tag} is unexpectedly large"
        )
    try:
        release = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemExit(
            f"the canonical GitHub Release metadata for {tag} is invalid"
        ) from error
    if not isinstance(release, dict):
        raise SystemExit(f"the canonical GitHub Release metadata for {tag} is invalid")
    return release


def verify_publication_evidence(revision: str, version: str) -> None:
    """Fail closed unless canonical tag and final Release bind this revision."""
    if VERSION_PATTERN.fullmatch(version) is None:
        raise SystemExit(f"the requested standard VERSION is invalid: {version!r}")
    tag = f"v{version}"
    if canonical_tag_revision(version) != revision:
        raise SystemExit(
            f"the standard release tag {tag} does not identify requested revision {revision}"
        )
    release = canonical_release(version)
    if release.get("tag_name") != tag:
        raise SystemExit(
            f"the canonical GitHub Release does not identify standard tag {tag}"
        )
    published_at = release.get("published_at")
    if (
        release.get("draft") is not False
        or release.get("prerelease") is not False
        or not isinstance(published_at, str)
        or not published_at.strip()
    ):
        raise SystemExit(
            f"the canonical GitHub Release {tag} is not a final published release"
        )


def package_files(root: Path, revision: str) -> list[dict[str, object]]:
    try:
        document = json.loads(git_bytes(root, revision, PACKAGE_MANIFEST))
    except json.JSONDecodeError as error:
        raise SystemExit(f"package manifest is not valid JSON: {error}") from error
    if set(document) != {"schema", "files"} or document["schema"] != "new-project.package-manifest/v1":
        raise SystemExit("package manifest must use new-project.package-manifest/v1")
    files = document["files"]
    if not isinstance(files, list) or not files:
        raise SystemExit("package manifest files must be a non-empty array")
    sources: set[str] = set()
    targets: set[str] = set()
    for index, item in enumerate(files):
        if not isinstance(item, dict) or set(item) != {"source", "target", "strategy", "executable"}:
            raise SystemExit(f"package manifest file {index} has invalid fields")
        source = item["source"]
        target = item["target"]
        strategy = item["strategy"]
        executable = item["executable"]
        if not isinstance(source, str) or not isinstance(target, str):
            raise SystemExit(f"package manifest file {index} paths must be strings")
        if any(Path(path).is_absolute() or ".." in Path(path).parts for path in (source, target)):
            raise SystemExit(f"package manifest file {index} paths must be repository-relative")
        if strategy not in {"managed", "seed", "extendable"} or not isinstance(executable, bool):
            raise SystemExit(f"package manifest file {index} has invalid strategy or executable flag")
        if strategy == "extendable" and ((source, target) not in ALLOWED_EXTENDABLE or executable):
            raise SystemExit(
                "extendable strategy currently supports only the target governance JSON manifest, "
                "required-checks instance and ticket-allocation policy"
            )
        if target in targets:
            raise SystemExit(f"duplicate package target: {target}")
        sources.add(source)
        targets.add(target)
        try:
            git_bytes(root, revision, source)
        except subprocess.CalledProcessError as error:
            raise SystemExit(f"package source is missing at {revision}: {source}") from error
    if PACKAGE_MANIFEST not in sources:
        raise SystemExit(f"package manifest must manage itself: {PACKAGE_MANIFEST}")
    entries = {str(item["target"]): item for item in files}
    extendable = entries.get(MANIFEST_TARGET)
    if extendable is not None and extendable["strategy"] == "extendable":
        base = entries.get(MANIFEST_BASE_TARGET)
        if base is None or base["strategy"] != "managed" or base["source"] != extendable["source"]:
            raise SystemExit("extendable target manifest requires a managed base from the same source")
    return files


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def load_json_bytes(content: bytes, label: str) -> object:
    try:
        return json.loads(content)
    except json.JSONDecodeError as error:
        raise SystemExit(f"{label} is not valid JSON: {error}") from error


def manifest_projection(content: bytes) -> bytes:
    """Return the standard-owned, canonical portion of a target manifest."""
    document = load_json_bytes(content, "standard manifest")
    if not isinstance(document, dict):
        raise SystemExit("standard manifest must be a JSON object")
    projection = json.loads(json.dumps(document))
    for parts in TARGET_OWNED_MANIFEST_PATHS:
        parent = projection
        for part in parts[:-1]:
            if not isinstance(parent, dict) or part not in parent:
                parent = None
                break
            parent = parent[part]
        if isinstance(parent, dict):
            parent.pop(parts[-1], None)
    return json_bytes(projection)


def extension_error(required: object, candidate: object, path: str = "$") -> str | None:
    if isinstance(required, dict):
        if not isinstance(candidate, dict):
            return f"{path} must remain an object"
        for key, value in required.items():
            if key not in candidate:
                return f"{path}/{key} is required by the managed base"
            error = extension_error(value, candidate[key], f"{path}/{key}")
            if error:
                return error
        return None
    if isinstance(required, list):
        if not isinstance(candidate, list):
            return f"{path} must remain an array"
        for value in required:
            if value not in candidate:
                return f"{path} removed a value required by the managed base"
        return None
    if candidate != required:
        return f"{path} differs from the managed base"
    return None


def merge_projection(previous: object, current: object, target: object, path: str = "$") -> object:
    """Three-way merge managed values while retaining target-owned extensions."""
    error = extension_error(previous, target, path)
    if error:
        raise SystemExit(f"target manifest violates its installed managed base: {error}")
    if isinstance(previous, dict):
        if not isinstance(current, dict) or not isinstance(target, dict):
            if target != previous:
                raise SystemExit(f"managed manifest type change conflicts at {path}")
            return current
        result = json.loads(json.dumps(target))
        for key, value in current.items():
            child_path = f"{path}/{key}"
            if key in previous:
                result[key] = merge_projection(previous[key], value, target[key], child_path)
            elif key not in target:
                result[key] = json.loads(json.dumps(value))
            else:
                error = extension_error(value, target[key], child_path)
                if error:
                    raise SystemExit(f"new managed manifest value conflicts with target extension: {error}")
        return result
    if isinstance(previous, list):
        if not isinstance(current, list) or not isinstance(target, list):
            if target != previous:
                raise SystemExit(f"managed manifest type change conflicts at {path}")
            return current
        result = json.loads(json.dumps(target))
        for value in current:
            if value not in result:
                result.append(json.loads(json.dumps(value)))
        return result
    return json.loads(json.dumps(current))


def existing_manifest_base(target_root: Path) -> bytes | None:
    """Load a trusted installed base or authenticated legacy target projection."""
    base_path = target_root / MANIFEST_BASE_TARGET
    lock_path = target_root / ".governance/manifest.lock.json"
    if not lock_path.is_file():
        return None
    lock = load_json_bytes(lock_path.read_bytes(), "existing governance lock")
    if not isinstance(lock, dict) or not isinstance(lock.get("managedFiles"), dict):
        raise SystemExit("existing governance lock has invalid managedFiles")
    managed = lock["managedFiles"]
    if base_path.is_file():
        expected = managed.get(MANIFEST_BASE_TARGET)
        actual = hashlib.sha256(base_path.read_bytes()).hexdigest()
        if expected != actual:
            raise SystemExit("installed manifest base differs from its governance lock")
        return base_path.read_bytes()

    manifest_path = target_root / MANIFEST_TARGET
    expected = managed.get(MANIFEST_TARGET)
    actual = hashlib.sha256(manifest_path.read_bytes()).hexdigest() if manifest_path.is_file() else None
    standard = lock.get("standard")
    revision = standard.get("sourceRevision") if isinstance(standard, dict) else None
    if expected != actual or not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        return None
    return manifest_projection(manifest_path.read_bytes())


def atomic_write(path: Path, content: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def lock_content(
    target_root: Path,
    revision: str,
    version: str,
    payloads: dict[str, bytes],
    managed_targets: set[str],
    publication_status: str,
) -> bytes:
    """Build the lock from expected payloads without requiring prior writes."""
    managed_hashes: dict[str, str] = {}
    for target in sorted(managed_targets):
        content = payloads.get(target)
        if content is None:
            content = (target_root / target).read_bytes()
        managed_hashes[target] = hashlib.sha256(content).hexdigest()

    lock = {
        "schema": "new-project.lock/v1",
        "standard": {
            "id": "wellmanifest/new-project",
            "version": version,
            "sourceRepository": "wellmanifest/new-project",
            "sourceRevision": revision,
            "publicationStatus": publication_status,
        },
        "managedFiles": managed_hashes,
    }
    return (json.dumps(lock, indent=2, sort_keys=True) + "\n").encode()


def worktree_ignore_payload(target_root: Path) -> bytes:
    """Append required root ignores without replacing target-owned rules."""
    target = target_root / ".gitignore"
    if target.is_symlink():
        raise SystemExit("root .gitignore must not be a symlink")
    content = target.read_bytes() if target.exists() else b""
    rules = [b"/.worktrees/"] + [
        f"/.subactor/{name}/".encode()
        for name in ("leases", "sessions", "recovery", "receipts", "cache", "snapshots")
    ]
    present = set(content.splitlines())
    missing = [rule for rule in rules if rule not in present]
    if not missing:
        return content
    if content and not content.endswith(b"\n"):
        content += b"\n"
    return content + b"\n# Repository-local worktrees and operational state\n" + b"\n".join(missing) + b"\n"


def planned_changes(
    target_root: Path,
    payloads: dict[str, bytes],
    expected_lock: bytes,
    executable_targets: set[str],
) -> list[tuple[str, str]]:
    """Return deterministic (action, path) entries for adoption drift."""
    changes: list[tuple[str, str]] = []
    for target, content in sorted(payloads.items()):
        path = target_root / target
        if not path.exists():
            changes.append(("CREATE", target))
        elif path.read_bytes() != content:
            changes.append(("UPDATE", target))
        elif target in executable_targets and not os.access(path, os.X_OK):
            changes.append(("CHMOD", target))

    lock_target = ".governance/manifest.lock.json"
    lock_path = target_root / lock_target
    if not lock_path.exists():
        changes.append(("CREATE", lock_target))
    elif lock_path.read_bytes() != expected_lock:
        changes.append(("UPDATE", lock_target))
    return changes


def missing_target_prerequisites(
    target_root: Path,
    manifest: object,
    payloads: dict[str, bytes],
) -> list[str]:
    """Return required files still absent after applying planned payloads."""
    if not isinstance(manifest, dict) or not isinstance(manifest.get("requiredFiles"), list):
        raise SystemExit("target manifest requiredFiles must be an array")
    required_files = manifest["requiredFiles"]
    missing: set[str] = set()
    for index, required in enumerate(required_files):
        if not isinstance(required, str) or not required:
            raise SystemExit(f"target manifest requiredFiles item {index} must be a non-empty string")
        path = Path(required)
        if path.is_absolute() or ".." in path.parts or path == Path("."):
            raise SystemExit(f"target manifest requiredFiles item {index} must be repository-relative")
        if required not in payloads and not (target_root / path).is_file():
            missing.add(required)
    return sorted(missing)


def ignored_payload_targets(target_root: Path, targets: set[str]) -> list[str]:
    """Return untracked package targets excluded by target Git ignore rules."""
    if not targets or not target_root.is_dir():
        return []
    work_tree = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=target_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if work_tree.returncode != 0 or work_tree.stdout.strip() != "true":
        return []
    encoded = b"".join(target.encode("utf-8") + b"\0" for target in sorted(targets))
    result = subprocess.run(
        ["git", "check-ignore", "--stdin", "-z"],
        cwd=target_root,
        input=encoded,
        capture_output=True,
        check=False,
    )
    if result.returncode not in {0, 1}:
        raise SystemExit("target Git ignore rules could not be evaluated safely")
    return sorted(
        path.decode("utf-8")
        for path in result.stdout.split(b"\0")
        if path
    )


def project_inherited_required_checks(
    target_root: Path,
    payloads: dict[str, bytes],
) -> None:
    """Replace only the hub's inherited check declaration with target truth.

    The package installs a governance workflow into every adopter.  Its check
    declaration must describe that workflow, rather than the hub's unrelated
    CI jobs.  A target-owned declaration is an extension and is never changed.
    """
    raw = payloads.get(CHECKS_TARGET)
    if raw is None:
        path = target_root / CHECKS_TARGET
        raw = path.read_bytes() if path.is_file() else None
    if raw is None:
        return
    document = load_json_bytes(raw, "target required-checks declaration")
    # Two declarations are unadapted seeds and must be projected from the
    # target's own workflows: the template marker, and the hub identity that
    # every adopter received while the seed was the hub's live instance.
    if not isinstance(document, dict) or document.get("repository") not in {
        UNRESOLVED_ADOPTER, "wellmanifest/new-project",
    }:
        return
    workflow_payloads = {
        target: content
        for target, content in payloads.items()
        if target.startswith(".github/workflows/")
    }
    generator_path = Path(__file__).resolve().with_name("generate_required_checks.py")
    spec = importlib.util.spec_from_file_location("new_project_required_checks", generator_path)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load the managed required-checks generator")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    derived = generator.declaration_for(
        target_root,
        ignored=(),
        workflow_payloads=workflow_payloads,
    )
    if derived is None:
        # A non-Git bootstrap has no authoritative repository identity. Keep
        # the source declaration rather than inventing one; a later adoption
        # in the real repository will project the local workflow truth.
        return
    callers = derived.get("reusableWorkflowCallers", [])
    if callers:
        raise SystemExit(
            "cannot project inherited required-checks through reusable workflow callers: "
            + ", ".join(str(value) for value in callers)
        )
    payloads[CHECKS_TARGET] = json_bytes(derived)


def report_missing_target_prerequisites(paths: list[str]) -> None:
    for path in paths:
        print(f"MISSING target prerequisite {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-root", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument(
        "--allow-unpublished-for-testing",
        action="store_true",
        help=(
            "Skip external publication proof only for bounded fixtures and "
            "record unpublished-test provenance"
        ),
    )
    parser.add_argument("--upgrade", action="store_true", help="Replace differing standard-managed files")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report adoption drift and planned changes without writing files",
    )
    args = parser.parse_args()

    if args.check and args.upgrade:
        parser.error("--check and --upgrade are mutually exclusive")

    if re.fullmatch(r"[0-9a-f]{40}", args.source_revision) is None:
        parser.error("--source-revision must be a full lowercase 40-character commit SHA")
    standard_root = Path(__file__).resolve().parent.parent
    target_root = Path(args.target_root).resolve()
    subprocess.run(
        ["git", "cat-file", "-e", f"{args.source_revision}^{{commit}}"],
        cwd=standard_root,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    version = git_bytes(standard_root, args.source_revision, "VERSION").decode().strip()
    publication_status = "unpublished-test"
    if not args.allow_unpublished_for_testing:
        verify_publication_evidence(args.source_revision, version)
        publication_status = "published"

    files = package_files(standard_root, args.source_revision)
    managed_targets = {
        str(item["target"]) for item in files if item["strategy"] == "managed"
    }
    executable_targets = {
        str(item["target"]) for item in files if item["executable"]
    }
    previous_base = existing_manifest_base(target_root)
    payloads: dict[str, bytes] = {}
    for item in files:
        target = str(item["target"])
        strategy = str(item["strategy"])
        source_content = git_bytes(standard_root, args.source_revision, str(item["source"]))
        if target == MANIFEST_BASE_TARGET:
            source_content = manifest_projection(source_content)
        target_path = target_root / target
        if strategy == "extendable" and not target_path.exists():
            payloads[target] = json_bytes(load_json_bytes(source_content, f"standard {target}"))
        elif strategy == "managed" or not target_path.exists():
            payloads[target] = source_content
        elif strategy == "extendable" and target == MANIFEST_TARGET:
            current_base = manifest_projection(source_content)
            target_document = load_json_bytes(target_path.read_bytes(), "target manifest")
            if previous_base is None:
                base_document = load_json_bytes(current_base, "managed manifest base")
                error = extension_error(base_document, target_document)
                if error:
                    raise SystemExit(f"target manifest does not extend the managed base: {error}")
                payloads[target] = target_path.read_bytes()
            else:
                payloads[target] = json_bytes(merge_projection(
                    load_json_bytes(previous_base, "previous managed manifest base"),
                    load_json_bytes(current_base, "current managed manifest base"),
                    target_document,
                ))
        elif strategy == "extendable":
            payloads[target] = target_path.read_bytes()
    manifest_path = target_root / ".governance/manifest.json"

    manifest_content = payloads.get(
        MANIFEST_TARGET,
        manifest_path.read_bytes() if manifest_path.exists() else b"",
    )
    try:
        manifest = json.loads(manifest_content)
    except json.JSONDecodeError as error:
        raise SystemExit(f"target manifest is not valid JSON: {error}") from error
    if manifest.get("standard", {}).get("version") != version:
        raise SystemExit(f"target manifest version must equal adopted standard version {version}")

    project_inherited_required_checks(target_root, payloads)
    payloads[".gitignore"] = worktree_ignore_payload(target_root)

    expected_lock = lock_content(
        target_root,
        args.source_revision,
        version,
        payloads,
        managed_targets,
        publication_status,
    )
    ignored_targets = ignored_payload_targets(target_root, set(payloads))
    if ignored_targets:
        raise SystemExit(
            "managed adoption targets are ignored by target Git rules; "
            "make them trackable before retrying: " + ", ".join(ignored_targets)
        )
    changes = planned_changes(target_root, payloads, expected_lock, executable_targets)
    missing_prerequisites = missing_target_prerequisites(target_root, manifest, payloads)

    if args.check:
        if not changes:
            print(f"up-to-date wellmanifest/new-project {version} at {args.source_revision}")
        else:
            for action, target in changes:
                print(f"{action} {target}")
            print(f"drift detected: {len(changes)} change(s) required")
        report_missing_target_prerequisites(missing_prerequisites)
        return 1 if changes or missing_prerequisites else 0

    # A complete payload is not a usable adoption when target-owned required
    # files are absent. Check the projected manifest before the first write,
    # including on upgrades that introduce new prerequisites.
    if missing_prerequisites:
        report_missing_target_prerequisites(missing_prerequisites)
        print("adoption blocked: supply target prerequisites before retrying; no files written")
        return 1

    conflicts = [
        target for target, content in payloads.items()
        if (target_root / target).exists() and (target_root / target).read_bytes() != content
    ]
    if conflicts and not args.upgrade:
        raise SystemExit(f"adoption files differ; rerun with --upgrade after review: {', '.join(sorted(conflicts))}")

    for target, content in sorted(payloads.items()):
        path = target_root / target
        if not path.exists() or path.read_bytes() != content:
            atomic_write(path, content, 0o755 if target in executable_targets else None)
        elif target in executable_targets and not os.access(path, os.X_OK):
            os.chmod(path, 0o755)
    atomic_write(
        target_root / ".governance/manifest.lock.json",
        expected_lock,
    )
    print(f"adopted wellmanifest/new-project {version} at {args.source_revision}")
    report_missing_target_prerequisites(missing_prerequisites)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
