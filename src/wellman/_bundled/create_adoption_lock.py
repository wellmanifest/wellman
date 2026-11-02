#!/usr/bin/env python3
"""Adopt an immutable new-project governance revision into a target repository."""

from __future__ import annotations

import argparse
import base64
import binascii
import contextlib
import fnmatch
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
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
    return subprocess.check_output(["git", "show", f"{revision}:{source}"], cwd=root,
                                   env=plan_git_environment())


def plan_git_environment() -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_NO_REPLACE_OBJECTS="1", GIT_OPTIONAL_LOCKS="0")
    return environment


ALLOCATION_PLAN_SCHEMA = "new-project.standard-adoption-plan/v1"


def plan_path(root: Path, name: str) -> Path:
    if (not name or Path(name).is_absolute() or Path(name).as_posix() != name
            or any(part in {"", ".", "..", ".git"} for part in name.split("/"))
            or any(character in name for character in "*?[]\\\x00\r\n")):
        raise SystemExit("adoption plan requires canonical literal repository paths")
    path = root / name
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise SystemExit("adoption plan refuses symlinked paths")
    return path


def plan_file(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    if not path.is_file():
        raise SystemExit("adoption plan requires regular files")
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            checksum.update(chunk)
    return {"sha256": checksum.hexdigest(), "mode": stat.S_IMODE(path.stat().st_mode)}


def plan_git(root: Path, *arguments: str) -> bytes:
    return subprocess.check_output(["git", "--no-optional-locks", *arguments], cwd=root,
                                   env=plan_git_environment(), stderr=subprocess.DEVNULL)


def allocation_target_state(root: Path, names: set[str]) -> dict[str, object]:
    if any(part.is_symlink() for part in (root, *root.parents)):
        raise SystemExit("adoption plan refuses symlinked repository roots")
    top = Path(os.fsdecode(plan_git(root, "rev-parse", "--show-toplevel")).strip())
    primary = os.fsdecode(plan_git(root, "worktree", "list", "--porcelain")).splitlines()[0]
    if (top != root or primary != "worktree " + str(root)
            or not (root / ".git").is_dir() or (root / ".git").is_symlink()):
        raise SystemExit("adoption plan requires the registered primary Git checkout")
    try:
        branch_ref = os.fsdecode(plan_git(root, "symbolic-ref", "HEAD")).strip()
        head = os.fsdecode(plan_git(root, "rev-parse", "--verify", "HEAD^{commit}")).strip()
        if branch_ref != "refs/heads/main":
            local_target = plan_git(root, "rev-parse", "--verify", "refs/heads/main^{commit}").strip()
            remote_target = plan_git(root, "rev-parse", "--verify", "refs/remotes/origin/main^{commit}").strip()
            if not branch_ref.startswith("refs/heads/") or local_target != head.encode() or remote_target != head.encode():
                raise SystemExit("adoption plan requires an exact named alias of local and origin main")
    except subprocess.CalledProcessError as error:
        raise SystemExit("adoption plan requires a named primary and complete target observations") from error
    branch = branch_ref.removeprefix("refs/heads/")
    status = plan_git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    fields = iter(os.fsdecode(status).split("\0"))
    dirty = set()
    for field in fields:
        if field:
            dirty.add(field[3:])
            if "R" in field[:2] or "C" in field[:2]:
                dirty.add(next(fields))
    index = root / ".git/index"
    if index.is_symlink():
        raise SystemExit("adoption plan refuses a symlinked Git index")
    return {
        "root": str(root), "head": head,
        "branch": branch, "statusSha256": hashlib.sha256(status).hexdigest(),
        "index": plan_file(index),
        "dirtyFiles": {name: plan_file(plan_path(root, name)) for name in sorted(dirty)},
        "files": {name: plan_file(plan_path(root, name)) for name in sorted(names)},
    }


def allocation_seed_ownership(root: Path, files: list[dict[str, object]],
                              source_manifest: dict, manifest: dict) -> list[str]:
    """Add exact absent/unowned incoming seeds, preserving every existing owner."""
    coordination = manifest["coordination"]
    streams = coordination["workstreams"]
    incoming = source_manifest["coordination"]["workstreams"]["governance"]["ownedPaths"]
    integration = coordination["integration"]
    additions = []
    for item in files:
        name = str(item["target"])
        if item["strategy"] != "seed" or (root / name).exists():
            continue
        if any(fnmatch.fnmatchcase(name, pattern) for stream in streams.values()
               for pattern in stream["ownedPaths"]):
            continue
        if (not any(fnmatch.fnmatchcase(name, pattern) for pattern in incoming)
                or any(fnmatch.fnmatchcase(name, pattern) for pattern in integration["requiredForPaths"])):
            raise SystemExit("incoming seed has no independently derived governance ownership")
        streams["governance"]["ownedPaths"].append(name)
        additions.append(name)
    return sorted(additions)


def allocation_delivery(manifest: dict, state: dict, scope: list[str],
                        previous: str, revision: str) -> dict:
    policy = manifest["delivery"]
    if policy.get("targetBranches") != ["main"] or "L" not in policy.get("allowedComplexityClasses", []):
        raise SystemExit("adoption allocation requires a supported declared delivery profile")
    profile = policy.get("profiles", {}).get("L", policy)
    return {
        "acceptedBaseSha": state["head"], "targetBranch": "main",
        "outcome": "Adopt the complete verified immutable wellmanifest/new-project package.",
        "nonGoals": ["Allocation grants no editing or publication authority",
                     "Preserve local overrides and unrelated implementation"],
        "complexity": "L", "estimatedMinutes": min(120, policy["maxActiveMinutes"]),
        "budgets": {"maxImplementationFiles": min(policy["maxImplementationFiles"], profile["maxImplementationFiles"]),
                    "maxAffectedComponents": 1, "maxPublicInterfaceChanges": 0, "maxRuntimeDependencies": 0},
        "architecture": {
            "status": "accepted", "decision": "Native allocation independently recomputes the exact published package and target state. Only its closed adoption paths are admitted; protected authority remains separate.",
            "components": [{"name": "immutable-standard-adoption", "paths": scope}],
            "responsibilityChanges": False, "interfaceChanges": [],
            "dataChanges": ["Immutable standard package and adoption lock"],
            "ui": {"impact": "none", "states": [], "evidence": []},
            "rollback": "Revert through protected review; preserve the previous immutable adoption pin.",
        },
        "runtimeDependencies": [],
        "validation": [{"criterion": "AC-01", "commands": ["./project/governance-check.sh"],
                        "evidence": "Complete immutable package, exact-base scope and independent protected publication"}],
        "standardAdoption": {"sourceRepository": "wellmanifest/new-project",
                             "fromRevision": previous, "toRevision": revision},
    }


def adoption_allocation_plan(standard_root: Path, revision: str, version: str,
                             target_root: Path, files: list[dict[str, object]],
                             payloads: dict[str, bytes], expected_lock: bytes,
                             executable: set[str], manifest: dict, before: dict,
                             additions: list[str]) -> dict:
    after = allocation_target_state(target_root, set(before["files"]))
    if before != after:
        raise SystemExit("target changed while preparing the adoption plan")
    old_lock = json.loads((target_root / ".governance/manifest.lock.json").read_bytes())
    standard = old_lock.get("standard", {})
    previous = standard.get("sourceRevision")
    if (standard.get("publicationStatus") != "published"
            or standard.get("sourceRepository") != "wellmanifest/new-project"
            or not isinstance(previous, str) or re.fullmatch(r"[0-9a-f]{40}", previous) is None
            or previous == revision):
        raise SystemExit("allocation plan requires a distinct published installed adoption")
    for name in (MANIFEST_TARGET, MANIFEST_BASE_TARGET, ".governance/manifest.lock.json",
                 ".governance/package-manifest.json"):
        if plan_git(target_root, "show", f"HEAD:{name}") != (target_root / name).read_bytes():
            raise SystemExit("current adoption metadata differs from the committed target base")
    strategies = {str(item["target"]): str(item["strategy"]) for item in files}
    owned = manifest["coordination"]["workstreams"]["governance"]["ownedPaths"]
    integration = manifest["coordination"]["integration"]["requiredForPaths"]
    changes = planned_changes(target_root, payloads, expected_lock, executable)
    scope = sorted({name for _action, name in changes})
    if not scope:
        raise SystemExit("adoption allocation plan has no material changes")
    old_managed = old_lock.get("managedFiles", {})
    if not isinstance(old_managed, dict) or not old_managed:
        raise SystemExit("installed adoption has no managed hash closure")
    for name, checksum in old_managed.items():
        current = plan_file(plan_path(target_root, name))
        if (not isinstance(checksum, str) or re.fullmatch(r"[0-9a-f]{64}", checksum) is None
                or current is None or current["sha256"] != checksum):
            raise SystemExit("installed managed closure differs from its adoption pin")
    old_package = json.loads((target_root / ".governance/package-manifest.json").read_bytes())
    old_strategies = {item["target"]: item["strategy"] for item in old_package["files"]}
    for name in scope:
        if strategies.get(name) == "managed":
            current = before["files"][name]
            if current is not None and (old_strategies.get(name) != "managed"
                    or old_managed.get(name) != current["sha256"]):
                raise SystemExit("managed adoption path requires explicit takeover or repair")
        elif (not any(fnmatch.fnmatchcase(name, pattern) for pattern in owned)
                or any(fnmatch.fnmatchcase(name, pattern) for pattern in integration)):
            raise SystemExit("adoption plan cannot transfer target-owned path: " + name)
    desired = {**payloads, ".governance/manifest.lock.json": expected_lock}
    def desired_mode(name, content):
        current = before["files"].get(name)
        if name != ".governance/manifest.lock.json" and current is not None and current["sha256"] == hashlib.sha256(content).hexdigest():
            mode = current["mode"]
            if name not in executable or mode & 0o111:
                return "100755" if mode & 0o100 else "100644"
        return "100755" if name in executable else "100644"
    plan = {
        "schema": ALLOCATION_PLAN_SCHEMA, "readOnly": True, "grantsAuthority": False,
        "source": {"repository": "wellmanifest/new-project", "revision": revision,
                   "version": version, "packageSha256": hashlib.sha256(git_bytes(standard_root, revision, PACKAGE_MANIFEST)).hexdigest(),
                   "exporterSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   "allocatorSha256": hashlib.sha256(git_bytes(standard_root, revision, "project/new-ticket.sh")).hexdigest()},
        "target": before, "prospectiveManifest": manifest, "ownershipAdditions": additions,
        "files": [{"path": name, "sha256": hashlib.sha256(content).hexdigest(),
                   "gitMode": desired_mode(name, content),
                   "strategy": strategies.get(name, "generated")}
                  for name, content in sorted(desired.items())],
        "allowedPaths": scope,
        "delivery": allocation_delivery(manifest, before, scope, previous, revision),
    }
    plan["digest"] = hashlib.sha256(json_bytes(plan)).hexdigest()
    return plan


def verify_allocation_plan(path: Path, target_root: Path, workstream: str,
                           requested_paths: list[str] | None = None) -> dict:
    """Recompute using this trusted package; never load executable paths from a plan."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise SystemExit("duplicate adoption allocation plan field")
            result[key] = value
        return result

    if (any(part.is_symlink() for part in (path, *path.parents))
            or not path.is_file() or path.stat().st_size > MAX_RELEASE_METADATA_BYTES):
        raise SystemExit("adoption allocation plan requires a bounded regular file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_RELEASE_METADATA_BYTES + 1)
    if len(raw) > MAX_RELEASE_METADATA_BYTES:
        raise SystemExit("adoption allocation plan exceeds size limit")
    try:
        plan = json.loads(raw, object_pairs_hook=pairs)
        revision = plan["source"]["revision"]
    except (ValueError, UnicodeError, KeyError, TypeError) as error:
        raise SystemExit("invalid adoption allocation plan") from error
    if (not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None
            or workstream != "governance"):
        raise SystemExit("invalid adoption allocation source or workstream")
    standard_root = Path(__file__).resolve().parent.parent
    if (standard_root / "project/new-ticket.sh").read_bytes() != git_bytes(standard_root, revision, "project/new-ticket.sh"):
        raise SystemExit("allocator differs from the immutable source package")
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        result = main(["--target-root", str(target_root), "--source-revision", revision,
                       "--check", "--allocation-plan"])
    if result != 0 or json_bytes(plan) != json_bytes(json.loads(output.getvalue())):
        raise SystemExit("adoption allocation plan changed or target state is stale")
    with path.open("rb") as stream:
        unchanged = stream.read(MAX_RELEASE_METADATA_BYTES + 1) == raw
    if not unchanged:
        raise SystemExit("adoption allocation plan changed during verification")
    if requested_paths is not None and requested_paths != plan["allowedPaths"]:
        raise SystemExit("caller scope differs from the exact derived adoption scope")
    return plan


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
        env=plan_git_environment(),
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
    has_python = (
        (target_root / "pyproject.toml").exists()
        or (target_root / "setup.py").exists()
        or (target_root / "setup.cfg").exists()
        or ((target_root / "packages").is_dir() and any((target_root / "packages").iterdir()))
    )
    if has_python:
        rules.extend([b"*.egg-info/", b"*.egg", b"build/", b"dist/"])
    if (target_root / "package.json").exists():
        rules.append(b"node_modules/")
    if (target_root / "Cargo.toml").exists():
        rules.append(b"/target/")
    present = set(content.splitlines())
    missing = [rule for rule in rules if rule not in present]
    if not missing:
        return content
    if content and not content.endswith(b"\n"):
        content += b"\n"
    return content + b"\n# Repository-local worktrees and operational state\n" + b"\n".join(missing) + b"\n"


def is_executable_file(path: Path) -> bool:
    if os.name == "nt":
        return True
    try:
        return bool(path.stat().st_mode & 0o111)
    except OSError:
        return False


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
        elif target in executable_targets and not is_executable_file(path):
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
        env=plan_git_environment(),
        cwd=target_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if work_tree.returncode != 0 or work_tree.stdout.strip() != "true":
        return []
    checkout = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=target_root,
        env=plan_git_environment(), capture_output=True, text=True, check=False,
    )
    if checkout.returncode != 0 or Path(checkout.stdout.strip()).resolve() != target_root.resolve():
        # An unborn scaffold inside another checkout has no Git ignore rules
        # of its own. Never borrow its ancestor's identity or ignored cache.
        return []
    encoded = b"".join(target.encode("utf-8") + b"\0" for target in sorted(targets))
    result = subprocess.run(
        ["git", "check-ignore", "--stdin", "-z"],
        env=plan_git_environment(),
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


def _git_show_blob(target_root: Path, ref: str, relative: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(target_root), "show", f"{ref}:{relative}"],
        capture_output=True,
        check=False,
    )


def _run_mirror_git(mirror: Path, git_env: dict[str, str], args: list[str]) -> None:
    subprocess.run(
        ["git", "-C", str(mirror), *args],
        env=git_env,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _git_cat_file_exists(target_root: Path, ref_path: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(target_root), "cat-file", "-e", ref_path],
        capture_output=True,
    )


def bootstrap_ownership_paths(
    target_root: Path,
    manifest: dict[str, object],
    package_targets: set[str],
    plan_path: Path,
) -> tuple[str, list[str]]:
    """Declare exact unowned prerequisites; never transfer an existing owner."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise SystemExit("duplicate bootstrap ownership plan key")
            result[key] = value
        return result

    if (any(path.is_symlink() for path in (plan_path, *plan_path.parents))
            or not plan_path.is_file() or plan_path.stat().st_size > MAX_RELEASE_METADATA_BYTES
            or target_root.resolve() in plan_path.resolve().parents):
        raise SystemExit("bootstrap ownership plan must be a bounded external regular file")
    try:
        plan = json.loads(plan_path.read_bytes(), object_pairs_hook=unique)
    except (ValueError, UnicodeDecodeError) as error:
        raise SystemExit("invalid bootstrap ownership plan JSON") from error
    if (not isinstance(plan, dict)
            or set(plan) != {"schema", "baseSha", "workstream", "paths"}
            or plan.get("schema") != "new-project.bootstrap-ownership-plan/v1"
            or not isinstance(plan.get("baseSha"), str)
            or re.fullmatch(r"[0-9a-f]{40}", plan["baseSha"]) is None):
        raise SystemExit("unsupported bootstrap ownership plan shape")
    workstreams = manifest["coordination"]["workstreams"]
    workstream = plan.get("workstream")
    if not isinstance(workstream, str) or workstream not in workstreams:
        raise SystemExit("bootstrap ownership plan requires a declared workstream")
    entries = plan.get("paths")
    if (not isinstance(entries, list) or not entries
            or len(entries) > manifest["delivery"]["maxImplementationFiles"]):
        raise SystemExit("bootstrap ownership plan paths exceed the declared implementation budget")
    head = subprocess.check_output(["git", "-C", str(target_root), "rev-parse", "HEAD"], text=True).strip()
    if head != plan["baseSha"]:
        raise SystemExit("bootstrap ownership plan is not bound to the current committed HEAD")
    paths = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "baseDigest"}:
            raise SystemExit("invalid bootstrap prerequisite binding")
        name, checksum = entry["path"], entry["baseDigest"]
        if (not isinstance(name, str) or not name or Path(name).is_absolute()
                or Path(name).as_posix() != name or any(part in {".", "..", ".git"} for part in name.split("/"))
                or any(character in name for character in "*?[\\")
                or not isinstance(checksum, str) or re.fullmatch(r"[0-9a-f]{64}", checksum) is None):
            raise SystemExit("unsafe bootstrap prerequisite path or digest")
        if name in paths or name in package_targets or name == ".gitignore":
            raise SystemExit("bootstrap prerequisite overlaps a package target or duplicate binding")
        if any(fnmatch.fnmatchcase(name, pattern) for stream in workstreams.values()
               for pattern in stream["ownedPaths"]):
            raise SystemExit("bootstrap prerequisite already has a declared owner")
        integration = manifest["coordination"]["integration"]
        if (workstream != integration["workstream"] and any(
                fnmatch.fnmatchcase(name, pattern) for pattern in integration["requiredForPaths"])):
            raise SystemExit("bootstrap prerequisite requires the integration workstream")
        path = target_root / name
        if any(part.is_symlink() for part in (path, *path.parents)) or not path.is_file():
            raise SystemExit("bootstrap prerequisite must match its exact regular-file digest")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != checksum:
            raise SystemExit("bootstrap prerequisite must match its exact regular-file digest")
        committed = _git_show_blob(target_root, head, name)
        if committed.returncode or committed.stdout != content:
            raise SystemExit("bootstrap prerequisite must match the committed base bytes")
        paths.append(name)
    return workstream, paths


def bootstrap_reusable_declaration(
    target_root: Path, payloads: dict[str, bytes], plan_path: Path,
    implementation_paths: list[str] | None = None,
) -> dict[str, object]:
    """Project future check names without writing or verifying target CI."""
    fields = {"schema", "baseSha", "callerFile", "callerSha256", "originalUses",
              "uses", "sourceFile", "sourceSha256", "sourceBase64"}
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise SystemExit("duplicate bootstrap reusable plan key")
            result[key] = value
        return result

    if (plan_path.is_symlink() or not plan_path.is_file()
            or plan_path.stat().st_size > 2 * 1024 * 1024
            or target_root.resolve() in plan_path.resolve().parents):
        raise SystemExit("bootstrap reusable plan must be a bounded external regular file")
    try:
        plan = json.loads(plan_path.read_bytes(), object_pairs_hook=unique)
    except (ValueError, UnicodeDecodeError) as error:
        raise SystemExit("invalid bootstrap reusable plan JSON") from error
    if (not isinstance(plan, dict) or set(plan) != fields
            or any(not isinstance(value, str) for value in plan.values())
            or plan["schema"] != "new-project.bootstrap-reusable-plan/v1"):
        raise SystemExit("unsupported bootstrap reusable plan shape")
    if (re.fullmatch(r"[0-9a-f]{40}", plan["baseSha"]) is None
            or any(re.fullmatch(r"[0-9a-f]{64}", plan[key]) is None
                   for key in ("callerSha256", "sourceSha256"))
            or re.fullmatch(r"\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml", plan["callerFile"]) is None
            or re.fullmatch(r"\.github/reusable-workflows/[A-Za-z0-9_.-]+\.ya?ml", plan["sourceFile"]) is None):
        raise SystemExit("unsafe bootstrap reusable plan identity or path")
    uses = re.fullmatch(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml)@([0-9a-f]{40})", plan["uses"])
    if uses is None or re.fullmatch(re.escape(uses[1]) + r"@[A-Za-z0-9_./-]+", plan["originalUses"]) is None:
        raise SystemExit("bootstrap callee must pin the same original workflow to a full SHA")
    if plan["callerFile"] in payloads:
        raise SystemExit("bootstrap plan cannot modify a managed workflow")
    for relative in (plan["callerFile"], plan["sourceFile"], ".github/reusable-workflows.lock.json"):
        candidate = target_root
        for part in Path(relative).parts:
            candidate /= part
            if candidate.is_symlink():
                raise SystemExit("symlinked bootstrap workflow path")
    if any((target_root / relative).exists() for relative in
           (plan["sourceFile"], ".github/reusable-workflows.lock.json")):
        raise SystemExit("existing reusable source contracts require ordinary adoption")
    head = subprocess.check_output(["git", "-C", str(target_root), "rev-parse", "HEAD"], text=True).strip()
    if head != plan["baseSha"]:
        raise SystemExit("bootstrap plan is not bound to the current committed HEAD")
    caller = target_root / plan["callerFile"]
    if not caller.is_file() or caller.stat().st_size > 1024 * 1024:
        raise SystemExit("missing or oversized bootstrap caller")
    committed = subprocess.run(["git", "-C", str(target_root), "show",
                                f'{head}:{plan["callerFile"]}'], capture_output=True)
    current = caller.read_bytes()
    if (committed.returncode or current != committed.stdout
            or hashlib.sha256(current).hexdigest() != plan["callerSha256"]):
        raise SystemExit("bootstrap caller must match the exact committed source bytes")
    try:
        source = base64.b64decode(plan["sourceBase64"], validate=True)
        source.decode("utf-8")
        text = current.decode("utf-8")
    except (ValueError, binascii.Error, UnicodeDecodeError) as error:
        raise SystemExit("invalid bootstrap workflow encoding") from error
    if len(source) > 1024 * 1024 or hashlib.sha256(source).hexdigest() != plan["sourceSha256"]:
        raise SystemExit("bootstrap callee source hash mismatch")
    line = re.compile(r"^    uses: " + re.escape(plan["originalUses"]) + r"[ \t]*$", re.M)
    if len(line.findall(text)) != 1:
        raise SystemExit("bootstrap plan requires one literal unquoted caller uses line")
    planned = line.sub("    uses: " + plan["uses"], text).encode("utf-8")
    spec = importlib.util.spec_from_file_location("bootstrap_checks", Path(__file__).with_name("generate_required_checks.py"))
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    repository = generator.repository_name(target_root)
    if not repository or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
        raise SystemExit("bootstrap reusable plan requires an authoritative origin identity")
    with tempfile.TemporaryDirectory(prefix="new-project-bootstrap-ci-") as directory:
        mirror = Path(directory)
        workflows = mirror / ".github/workflows"
        workflows.mkdir(parents=True)
        for path in sorted((target_root / ".github/workflows").glob("*.y*ml")):
            if path.is_symlink() or not path.is_file():
                raise SystemExit("unsafe target workflow in bootstrap plan")
            (workflows / path.name).write_bytes(path.read_bytes())
        for relative, content in payloads.items():
            if relative.startswith(".github/workflows/"):
                (mirror / relative).write_bytes(content)
        (mirror / plan["callerFile"]).write_bytes(planned)
        callee = mirror / plan["sourceFile"]
        callee.parent.mkdir()
        callee.write_bytes(source)
        entry = {key: plan[key] for key in ("uses", "sourceFile", "sourceSha256")}
        (mirror / ".github/reusable-workflows.lock.json").write_bytes(json_bytes({
            "schema": "new-project.reusable-workflows/v1", "workflows": [entry]}))
        git_env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        for args in (["init", "-q"], ["remote", "add", "origin", f"https://github.com/{repository}.git"]):
            _run_mirror_git(mirror, git_env, args)
        derived = generator.declaration_for(mirror, ignored=())
        if (derived is None or derived["repository"] != repository
                or derived.get("reusableWorkflowCallers")):
            raise SystemExit("bootstrap plan leaves unresolved workflow callers")
    print(f'PLANNED {plan["callerFile"]} uses {plan["uses"]}; target CI unchanged and unverified')
    if implementation_paths is not None:
        implementation_paths.extend([plan["callerFile"], plan["sourceFile"],
                                     ".github/reusable-workflows.lock.json"])
    return derived


def project_inherited_required_checks(
    target_root: Path,
    payloads: dict[str, bytes],
    bootstrap_plan: Path | None = None,
    implementation_paths: list[str] | None = None,
    repository: str | None = None,
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
        if bootstrap_plan is not None:
            raise SystemExit("bootstrap plan cannot replace a target-owned check declaration")
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
    origin = generator.repository_name(target_root)
    if repository is not None and origin is not None and origin.casefold() != repository.casefold():
        raise SystemExit(f"--repository {repository} disagrees with origin {origin}")
    derived = (bootstrap_reusable_declaration(target_root, workflow_payloads, bootstrap_plan,
                                              implementation_paths)
               if bootstrap_plan is not None else generator.declaration_for(
                   target_root, ignored=(), workflow_payloads=workflow_payloads,
                   repository=repository))
    if derived is None:
        # A target without an origin remote or --repository has no
        # authoritative identity. Keep the source declaration rather than
        # inventing one, and say so: the first material PR fails GOV-SYNC-001
        # until a rerun binds the name.
        if document.get("repository") == UNRESOLVED_ADOPTER:
            print(f"UNBOUND {CHECKS_TARGET} keeps {UNRESOLVED_ADOPTER}: no origin remote; "
                  "rerun with --repository OWNER/NAME or after git remote add origin", file=sys.stderr)
        return
    # A display name is not source identity. Even a caller named governance
    # must bind its actual callee before we can project its published checks.
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


def validate_wellman_scaffold(target_root: Path, files: list[dict[str, object]]) -> None:
    """Accept only an explicit, policy-free legacy baseline initialization."""
    targets = {str(item["target"]) for item in files}
    targets.update({".gitignore", ".governance/manifest.lock.json"})
    for target in targets:
        path = target_root / target
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise SystemExit("Wellman scaffold migration refuses symlinked target paths")
    for name in ("manifest.base.json", "package-manifest.json"):
        if (target_root / ".governance" / name).exists():
            raise SystemExit("Wellman scaffold migration refuses existing native adoption evidence")

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate manifest key")
            result[key] = value
        return result

    try:
        document = json.loads((target_root / MANIFEST_TARGET).read_bytes(), object_pairs_hook=unique_object)
    except (OSError, ValueError, UnicodeError) as error:
        raise SystemExit("migration requires the exact minimal Wellman baseline scaffold") from error
    standard = document.get("standard") if isinstance(document, dict) else None
    if not (
        isinstance(document, dict) and set(document) == {"schema", "standard"}
        and document["schema"] == "wellmanifest.manifest/v1"
        and isinstance(standard, dict) and set(standard) == {"id", "version"}
        and standard["id"] == "profile:baseline"
        and isinstance(standard["version"], str) and VERSION_PATTERN.fullmatch(standard["version"])
    ):
        raise SystemExit("migration requires the exact minimal Wellman baseline scaffold")

    lock_path = target_root / ".governance/manifest.lock.json"
    if not lock_path.exists():
        return
    # A baseline registration is not a complete native adoption. Accept only
    # its closed seven-file inventory, already committed at the target HEAD.
    legacy_paths = {
        "AGENTS.md", "GEMINI.md", ".governance/manifest.json",
        ".governance/standard-requirements.json", ".governance/standard-packs.json",
        ".governance/docs.json", ".governance/local-ci-publication.json",
    }
    try:
        lock = json.loads(lock_path.read_bytes(), object_pairs_hook=unique_object)
        standard = lock.get("standard") if isinstance(lock, dict) else None
        managed = lock.get("managedFiles") if isinstance(lock, dict) else None
        if not (
            isinstance(lock, dict) and set(lock) == {"schema", "standard", "managedFiles"}
            and lock["schema"] == "new-project.lock/v1"
            and isinstance(standard, dict)
            and set(standard) == {"id", "sourceRepository", "sourceRevision", "version", "publicationStatus"}
            and standard["id"] == standard["sourceRepository"] == "wellmanifest/new-project"
            and standard["publicationStatus"] == "published"
            and isinstance(standard["version"], str) and VERSION_PATTERN.fullmatch(standard["version"])
            and isinstance(standard["sourceRevision"], str) and re.fullmatch(r"[0-9a-f]{40}", standard["sourceRevision"])
            and isinstance(managed, dict) and set(managed) == legacy_paths
        ):
            raise ValueError("not the closed legacy inventory")
        for relative in sorted(legacy_paths | {".governance/manifest.lock.json"}):
            path = target_root / relative
            if any(part.is_symlink() for part in (path, *path.parents)):
                raise ValueError("symlinked registration")
            content = path.read_bytes()
            if relative in managed and (
                not isinstance(managed[relative], str)
                or re.fullmatch(r"[0-9a-f]{64}", managed[relative]) is None
                or hashlib.sha256(content).hexdigest() != managed[relative]
            ):
                raise ValueError("registration digest mismatch")
            committed = _git_show_blob(target_root, "HEAD", relative)
            if committed.returncode or committed.stdout != content:
                raise ValueError("registration differs from committed target bytes")
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise SystemExit("Wellman scaffold migration refuses existing native adoption evidence or invalid legacy registration") from error


def main(argv: list[str] | None = None) -> int:
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
        "--migrate-wellman-scaffold", action="store_true",
        help="Explicitly initialize native governance over the exact minimal legacy Wellman baseline scaffold",
    )
    parser.add_argument(
        "--bootstrap-native-adoption", action="store_true",
        help="Record first-allocation bootstrap for a committed repository without governance",
    )
    parser.add_argument("--bootstrap-reusable-plan", type=Path,
                        help="External exact-state future reusable CI plan; never edits target workflows")
    parser.add_argument("--bootstrap-ownership-plan", type=Path,
                        help="External exact-base/digest plan declaring only existing unowned prerequisites")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report adoption drift and planned changes without writing files",
    )
    parser.add_argument("--allocation-plan", action="store_true",
                        help="With --check, export a read-only exact-state native upgrade allocation plan")
    parser.add_argument("--repository", metavar="OWNER/NAME",
                        help="Bind required checks to this repository before an origin remote exists")
    args = parser.parse_args(argv)

    if args.allocation_plan and (not args.check or args.allow_unpublished_for_testing
            or args.bootstrap_native_adoption or args.migrate_wellman_scaffold
            or args.bootstrap_reusable_plan or args.bootstrap_ownership_plan):
        parser.error("--allocation-plan requires --check and a published native upgrade")

    if args.check and args.upgrade:
        parser.error("--check and --upgrade are mutually exclusive")
    if args.migrate_wellman_scaffold and not (args.check or args.upgrade):
        parser.error("--migrate-wellman-scaffold requires --check or --upgrade after review")
    if args.bootstrap_native_adoption and args.migrate_wellman_scaffold:
        parser.error("fresh bootstrap and scaffold migration are mutually exclusive")
    if args.bootstrap_reusable_plan and not (args.bootstrap_native_adoption or args.migrate_wellman_scaffold):
        parser.error("a reusable CI bootstrap plan requires explicit fresh native bootstrap or scaffold migration")
    if args.bootstrap_ownership_plan and not (args.bootstrap_native_adoption or args.migrate_wellman_scaffold):
        parser.error("a prerequisite ownership plan requires explicit fresh native bootstrap or scaffold migration")

    if re.fullmatch(r"[0-9a-f]{40}", args.source_revision) is None:
        parser.error("--source-revision must be a full lowercase 40-character commit SHA")
    if args.repository is not None and (
            re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository) is None
            or args.repository == UNRESOLVED_ADOPTER):
        parser.error("--repository must be OWNER/NAME")
    standard_root = Path(__file__).resolve().parent.parent
    requested_root = Path(args.target_root).absolute()
    if (args.migrate_wellman_scaffold or args.bootstrap_native_adoption or args.allocation_plan) and any(
        path.is_symlink() for path in (requested_root, *requested_root.parents)
    ):
        raise SystemExit("Wellman scaffold migration refuses symlinked target paths")
    target_root = requested_root.resolve()
    if args.allocation_plan and ".." in Path(args.target_root).parts:
        raise SystemExit("adoption plan refuses traversal in target roots")
    fresh_base_sha = None
    if args.bootstrap_native_adoption:
        for name in ("manifest.json", "manifest.lock.json", "manifest.base.json", "package-manifest.json"):
            path = target_root / ".governance" / name
            if path.exists() or path.is_symlink():
                raise SystemExit("fresh bootstrap requires absent governance; use its existing adoption route")
        observed = subprocess.run(["git", "-C", str(target_root), "rev-parse", "HEAD"],
                                  capture_output=True, text=True)
        if observed.returncode:
            raise SystemExit("fresh bootstrap requires a committed Git repository")
        fresh_base_sha = observed.stdout.strip()
        checkout = subprocess.check_output(
            ["git", "-C", str(target_root), "rev-parse", "--show-toplevel"], text=True).strip()
        if Path(checkout).resolve() != target_root:
            raise SystemExit("fresh bootstrap requires the repository checkout root")
        for name in ("manifest.json", "manifest.lock.json", "manifest.base.json", "package-manifest.json"):
            present = _git_cat_file_exists(target_root, f"HEAD:.governance/{name}")
            if present.returncode == 0:
                raise SystemExit("fresh bootstrap cannot replace committed governance")
    subprocess.run(
        ["git", "cat-file", "-e", f"{args.source_revision}^{{commit}}"],
        env=plan_git_environment(),
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
    plan_before = None
    if args.allocation_plan:
        if Path(__file__).read_bytes() != git_bytes(standard_root, args.source_revision, "scripts/create_adoption_lock.py"):
            raise SystemExit("plan exporter differs from the immutable source package")
        old_lock = json.loads(plan_path(target_root, ".governance/manifest.lock.json").read_bytes())
        old_managed = old_lock.get("managedFiles")
        if not isinstance(old_managed, dict):
            raise SystemExit("adoption plan requires an installed managed hash closure")
        plan_before = allocation_target_state(target_root,
            {str(item["target"]) for item in files} | set(old_managed)
            | {".governance/manifest.lock.json", ".gitignore"})
    if args.migrate_wellman_scaffold:
        validate_wellman_scaffold(target_root, files)
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
            if args.migrate_wellman_scaffold:
                payloads[target] = json_bytes(load_json_bytes(source_content, "standard manifest"))
                continue
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

    seed_additions: list[str] = []
    if previous_base is not None and "governance" in manifest["coordination"]["workstreams"]:
        seed_additions = allocation_seed_ownership(target_root, files,
            json.loads(git_bytes(standard_root, args.source_revision, MANIFEST_SOURCE)), manifest)
        if seed_additions:
            payloads[MANIFEST_TARGET] = json_bytes(manifest)

    bootstrap_paths: list[str] = []
    project_inherited_required_checks(target_root, payloads, args.bootstrap_reusable_plan,
                                     bootstrap_paths, args.repository)
    if bootstrap_paths:
        # These three exact target paths need an owner before real allocation.
        # This is a target manifest declaration, never a writer/merge grant.
        owned_paths = manifest["coordination"]["workstreams"]["governance"]["ownedPaths"]
        owned_paths.extend(path for path in bootstrap_paths if path not in owned_paths)
        payloads[MANIFEST_TARGET] = json_bytes(manifest)
    ownership_base = json.loads(json.dumps(manifest))
    ownership = None
    if args.bootstrap_ownership_plan:
        ownership = bootstrap_ownership_paths(target_root, ownership_base,
            {str(item["target"]) for item in files}, args.bootstrap_ownership_plan)
        stream, paths = ownership
        manifest["coordination"]["workstreams"][stream]["ownedPaths"].extend(paths)
        payloads[MANIFEST_TARGET] = json_bytes(manifest)
        for path in paths:
            print(f"PLANNED prerequisite ownership {stream}: {path}; no writer or publication authority")
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

    if args.allocation_plan:
        if missing_prerequisites:
            raise SystemExit("adoption allocation requires all target prerequisites")
        assert plan_before is not None
        print(json.dumps(adoption_allocation_plan(standard_root, args.source_revision, version,
            target_root, files, payloads, expected_lock, executable_targets, manifest,
            plan_before, seed_additions), sort_keys=True))
        return 0

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

    bootstrap_head = None
    if args.migrate_wellman_scaffold or args.bootstrap_native_adoption:
        receipt = target_root / ".subactor/receipts/bootstrap-adoption.json"
        if any(path.is_symlink() for path in (receipt, *receipt.parents)):
            raise SystemExit("bootstrap receipt path is symlinked")
        if any(path.exists() and not path.is_dir() for path in receipt.parents):
            raise SystemExit("bootstrap receipt parent is not a directory")
        observed = subprocess.run(["git", "-C", str(target_root), "rev-parse", "HEAD"],
                                  capture_output=True, text=True)
        if observed.returncode == 0:
            bootstrap_head = observed.stdout.strip()
        if fresh_base_sha is not None and bootstrap_head != fresh_base_sha:
            raise SystemExit("repository HEAD changed before bootstrap; reconcile ownership")
        if args.migrate_wellman_scaffold:
            validate_wellman_scaffold(target_root, files)
    if ownership is not None:
        if bootstrap_ownership_paths(target_root, ownership_base,
                {str(item["target"]) for item in files}, args.bootstrap_ownership_plan) != ownership:
            raise SystemExit("bootstrap ownership plan changed before writes")
    for target, content in sorted(payloads.items()):
        path = target_root / target
        if not path.exists() or path.read_bytes() != content:
            atomic_write(path, content, 0o755 if target in executable_targets else None)
        elif target in executable_targets and not is_executable_file(path):
            os.chmod(path, 0o755)
    atomic_write(
        target_root / ".governance/manifest.lock.json",
        expected_lock,
    )
    if args.migrate_wellman_scaffold or args.bootstrap_native_adoption:
        # Local ownership acknowledgement is not writer or publication authority.
        result = subprocess.run(["git", "-C", str(target_root), "rev-parse", "HEAD"],
                                capture_output=True, text=True)
        if result.returncode == 0 and bootstrap_head:
            if result.stdout.strip() != bootstrap_head:
                raise SystemExit("repository HEAD changed during bootstrap; reconcile installed files")
            owned = dict(payloads)
            owned[".governance/manifest.lock.json"] = expected_lock
            for rel in manifest.get("requiredFiles", []):
                before = _git_cat_file_exists(target_root, f"HEAD:{rel}")
                path = target_root / rel
                if before.returncode and path.is_file() and not path.is_symlink():
                    owned.setdefault(rel, path.read_bytes())
            receipt = target_root / ".subactor/receipts/bootstrap-adoption.json"
            if any(path.is_symlink() for path in (receipt, *receipt.parents)):
                raise SystemExit("bootstrap receipt path is symlinked")
            common = subprocess.check_output(
                ["git", "-C", str(target_root), "rev-parse", "--path-format=absolute",
                 "--git-common-dir"], text=True).strip()
            atomic_write(receipt, (json.dumps({
                "schema": "new-project.bootstrap-adoption/v1",
                "baseSha": result.stdout.strip(), "commonGitDir": common,
                "sourceRevision": args.source_revision,
                "bootstrapKind": "fresh" if args.bootstrap_native_adoption else "legacy-scaffold",
                "files": {rel: hashlib.sha256(data).hexdigest()
                          for rel, data in sorted(owned.items())},
                "grantsWriterAuthority": False, "grantsPublicationAuthority": False,
            }, indent=2, sort_keys=True) + "\n").encode())
    agent_hosts_script = target_root / "scripts/install-agent-hosts.sh"
    if agent_hosts_script.is_file() and (target_root / ".git").exists():
        try:
            cmd = [str(agent_hosts_script), "--target", str(target_root)]
            if os.name != "nt":
                if is_executable_file(agent_hosts_script):
                    subprocess.run(cmd, cwd=target_root, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif shutil.which("bash"):
                    subprocess.run(["bash"] + cmd, cwd=target_root, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                bash_path = shutil.which("bash")
                if bash_path:
                    subprocess.run([bash_path] + cmd, cwd=target_root, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    dsl_render_script = target_root / ".governance/render_dsl_manifest.py"
    if dsl_render_script.is_file():
        try:
            subprocess.run(
                [sys.executable, str(dsl_render_script)],
                cwd=target_root,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
    print(f"adopted wellmanifest/new-project {version} at {args.source_revision}")
    report_missing_target_prerequisites(missing_prerequisites)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
