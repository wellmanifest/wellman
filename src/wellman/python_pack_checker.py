"""Dependency-free S1 static conformance checker for wellmanifest/python.

Enforces the normative distribution and runtime parity rules without executing
repository code:
- PYTHON-DIST-001: Commit-artifact & version parity (pyproject.toml vs VERSION,
  newest wheel version match, and byte-for-byte source/wheel .py parity).
- PYTHON-DIST-002: CLI entry-point target verification and --version flag contract.
- PYTHON-DIST-003: Wheel archive integrity/bounds and missing source module
  detection (build_file_missing).
"""

from __future__ import annotations

import ast
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]

from wellman.validator import Finding

_MAX_FILE_BYTES = 2 * 1024 * 1024
_MAX_WHEEL_BYTES = 64 * 1024 * 1024
_MAX_WHEEL_MEMBERS = 4096
_MAX_WHEEL_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox",
    "node_modules", "build", "dist", ".eggs", ".worktrees", ".subactor",
    "tests", "test",
})
_ENTRYPOINT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*):([A-Za-z_][A-Za-z0-9_.]*)$")


def _has_symlink_component(root: Path, candidate: Path) -> bool:
    if candidate.is_symlink():
        return True
    try:
        rel = candidate.relative_to(root)
    except ValueError:
        return True
    cur = root
    for part in rel.parts:
        cur = cur / part
        if cur.is_symlink():
            return True
    return False


def _read_bounded_bytes(root: Path, path: Path, max_bytes: int = _MAX_FILE_BYTES) -> Tuple[Optional[bytes], Optional[str]]:
    if _has_symlink_component(root, path):
        return None, "refusing symlinked path"
    try:
        st = path.stat()
    except OSError as exc:
        return None, f"cannot stat file: {exc}"
    if st.st_size > max_bytes:
        return None, f"file exceeds {max_bytes} byte limit ({st.st_size} bytes)"
    try:
        data = path.read_bytes()
    except OSError as exc:
        return None, f"cannot read file: {exc}"
    if len(data) > max_bytes:
        return None, f"file exceeds {max_bytes} byte limit"
    return data, None


def _parse_pyproject_fallback(text: str) -> Dict[str, Any]:
    """Minimal fallback parser for Python < 3.11 environments without tomllib."""
    section = ""
    project: Dict[str, Any] = {}
    scripts: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if "=" not in line:
            continue
        key, val = [p.strip() for p in line.split("=", 1)]
        key = key.strip("\"'")
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            unquoted = val[1:-1]
            if section == "project" and key in ("name", "version"):
                project[key] = unquoted
            elif section == "project.scripts":
                scripts[key] = unquoted
    if scripts:
        project["scripts"] = scripts
    return {"project": project} if project else {}


def _load_pyproject(root: Path, pyproject_path: Path) -> Tuple[Optional[Dict[str, Any]], List[Finding]]:
    raw, err = _read_bounded_bytes(root, pyproject_path)
    if err is not None or raw is None:
        return None, [Finding(
            code="PYTHON-DIST-001",
            message=f"Cannot read pyproject.toml safely: {err}",
            path="pyproject.toml",
            remediation="Ensure pyproject.toml is a bounded regular UTF-8 TOML file.",
        )]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, [Finding(
            code="PYTHON-DIST-001",
            message=f"pyproject.toml is not valid UTF-8: {exc}",
            path="pyproject.toml",
            remediation="Encode pyproject.toml as valid UTF-8.",
        )]
    if tomllib is not None:
        try:
            doc = tomllib.loads(text)
        except Exception as exc:
            return None, [Finding(
                code="PYTHON-DIST-001",
                message=f"Invalid TOML syntax in pyproject.toml: {exc}",
                path="pyproject.toml",
                remediation="Fix TOML syntax errors in pyproject.toml.",
            )]
        if not isinstance(doc, dict):
            return None, [Finding(
                code="PYTHON-DIST-001",
                message="pyproject.toml root must be a TOML table.",
                path="pyproject.toml",
                remediation="Ensure pyproject.toml parses to a top-level mapping.",
            )]
        return doc, []
    return _parse_pyproject_fallback(text), []


def _discover_source_packages(root: Path, doc: Dict[str, Any]) -> List[Tuple[str, Path]]:
    """Return (package_rel_prefix, fs_package_dir) pairs for importable Python packages."""
    candidates: List[Path] = []
    src_dir = root / "src"
    if src_dir.is_dir() and not _has_symlink_component(root, src_dir):
        candidates.append(src_dir)
    else:
        candidates.append(root)

    packages: List[Tuple[str, Path]] = []
    seen = set()
    for base in candidates:
        try:
            entries = sorted(base.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for entry in entries:
            if entry.name in _SKIP_DIRS or entry.name.startswith(".") or entry.name.endswith(".egg-info"):
                continue
            if _has_symlink_component(root, entry) or not entry.is_dir():
                continue
            init_py = entry / "__init__.py"
            if init_py.is_file() and not _has_symlink_component(root, init_py):
                if entry.name not in seen:
                    seen.add(entry.name)
                    packages.append((entry.name, entry))
    return packages


def _resolve_module_file(root: Path, module_path: str) -> Optional[Path]:
    parts = module_path.split(".")
    if any(not p or p in {".", ".."} for p in parts):
        return None
    for prefix in (root / "src", root):
        mod_file = prefix.joinpath(*parts).with_suffix(".py")
        if mod_file.is_file() and not _has_symlink_component(root, mod_file):
            return mod_file
        pkg_init = prefix.joinpath(*parts, "__init__.py")
        if pkg_init.is_file() and not _has_symlink_component(root, pkg_init):
            return pkg_init
    return None


def _module_defines_symbol(source_text: str, attr_chain: str) -> bool:
    top_attr = attr_chain.split(".", 1)[0]
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return False
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == top_attr:
            return True
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == top_attr:
                    return True
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == top_attr:
            return True
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                if bound == top_attr or alias.name == "*":
                    return True
    return False


def _check_cli_scripts(root: Path, doc: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []
    project = doc.get("project")
    if not isinstance(project, dict):
        return findings
    scripts = project.get("scripts")
    if scripts is None:
        return findings
    if not isinstance(scripts, dict):
        return [Finding(
            code="PYTHON-DIST-002",
            message="[project.scripts] in pyproject.toml must be a table mapping CLI names to module:callable targets.",
            path="pyproject.toml",
            remediation="Declare valid CLI entry points under [project.scripts].",
        )]
    for cli_name, target in sorted(scripts.items()):
        if not isinstance(target, str) or not _ENTRYPOINT_RE.fullmatch(target.strip()):
            findings.append(Finding(
                code="PYTHON-DIST-002",
                message=f"CLI script '{cli_name}' has invalid entry-point target '{target}'.",
                path="pyproject.toml",
                remediation="Use 'package.module:callable' syntax in [project.scripts].",
            ))
            continue
        mod_name, attr_name = target.strip().split(":", 1)
        mod_file = _resolve_module_file(root, mod_name)
        if mod_file is None:
            findings.append(Finding(
                code="PYTHON-DIST-002",
                message=f"CLI script '{cli_name}' points to missing module '{mod_name}'.",
                path="pyproject.toml",
                remediation=f"Create '{mod_name}' or update [project.scripts] in pyproject.toml.",
            ))
            continue
        raw, err = _read_bounded_bytes(root, mod_file)
        rel_mod = str(mod_file.relative_to(root))
        if err is not None or raw is None:
            findings.append(Finding(
                code="PYTHON-DIST-002",
                message=f"Cannot inspect CLI module '{rel_mod}': {err}",
                path=rel_mod,
                remediation="Ensure the CLI entry-point module is a readable regular Python file.",
            ))
            continue
        source_text = raw.decode("utf-8", errors="replace")
        if not _module_defines_symbol(source_text, attr_name):
            findings.append(Finding(
                code="PYTHON-DIST-002",
                message=f"CLI script '{cli_name}' target '{attr_name}' is not defined in '{rel_mod}'.",
                path=rel_mod,
                remediation=f"Define '{attr_name}' in '{rel_mod}' or fix [project.scripts].",
            ))
            continue
        if "--version" not in source_text and "version_probe" not in source_text:
            findings.append(Finding(
                code="PYTHON-DIST-002",
                message=f"CLI entry-point '{cli_name}' ({rel_mod}) does not expose '--version' introspection.",
                severity="WARNING",
                path=rel_mod,
                remediation="Support '--version' reporting source version, installed metadata, and dist artifact parity (PYTHON-DIST-002).",
            ))
    return findings


def _extract_wheel_version(wheel_name: str, zf: zipfile.ZipFile) -> Optional[str]:
    for name in zf.namelist():
        if name.endswith(".dist-info/METADATA") and name.count("/") == 1:
            meta_text = zf.read(name).decode("utf-8", errors="replace")
            for line in meta_text.splitlines():
                if line.startswith("Version:"):
                    return line.split(":", 1)[1].strip()
    parts = wheel_name[:-4].split("-") if wheel_name.endswith(".whl") else []
    return parts[1] if len(parts) >= 2 else None


def _check_dist_wheels(
    root: Path,
    declared_version: Optional[str],
    packages: List[Tuple[str, Path]],
) -> List[Finding]:
    findings: List[Finding] = []
    dist_dir = root / "dist"
    if not dist_dir.exists():
        return findings
    if _has_symlink_component(root, dist_dir) or not dist_dir.is_dir():
        return [Finding(
            code="PYTHON-DIST-003",
            message="dist/ must be a regular directory inside the repository.",
            path="dist",
            remediation="Replace symlinked or non-directory dist path with a regular directory.",
        )]

    wheels: List[Tuple[Tuple[int, str], Path]] = []
    try:
        entries = list(dist_dir.iterdir())
    except OSError as exc:
        return [Finding(
            code="PYTHON-DIST-003",
            message=f"Cannot list dist/ directory: {exc}",
            path="dist",
            remediation="Restore read permissions on dist/.",
        )]

    for entry in entries:
        if not entry.name.endswith(".whl"):
            continue
        rel_whl = f"dist/{entry.name}"
        if _has_symlink_component(root, entry) or not entry.is_file():
            findings.append(Finding(
                code="PYTHON-DIST-003",
                message=f"Wheel artifact '{rel_whl}' must be a regular non-symlink file.",
                path=rel_whl,
                remediation="Rebuild wheel artifacts as regular files in dist/.",
            ))
            continue
        st = entry.stat()
        if st.st_size > _MAX_WHEEL_BYTES:
            findings.append(Finding(
                code="PYTHON-DIST-003",
                message=f"Wheel artifact '{rel_whl}' exceeds {_MAX_WHEEL_BYTES} byte safety bound.",
                path=rel_whl,
                remediation="Inspect oversized wheel artifact in dist/.",
            ))
            continue
        wheels.append(((st.st_mtime_ns, entry.name), entry))

    if not wheels:
        return findings

    wheels.sort(key=lambda item: item[0])
    newest_wheel = wheels[-1][1]
    rel_newest = f"dist/{newest_wheel.name}"

    try:
        with zipfile.ZipFile(newest_wheel, "r") as zf:
            infos = zf.infolist()
            if len(infos) > _MAX_WHEEL_MEMBERS:
                return findings + [Finding(
                    code="PYTHON-DIST-003",
                    message=f"Wheel '{rel_newest}' has {len(infos)} entries (limit {_MAX_WHEEL_MEMBERS}).",
                    path=rel_newest,
                    remediation="Rebuild clean wheel artifact without excessive entries.",
                )]
            total_uncompressed = 0
            wheel_py_files: Dict[str, bytes] = {}
            for info in infos:
                norm_name = info.filename.replace("\\", "/")
                parts = [p for p in norm_name.split("/") if p]
                if norm_name.startswith("/") or ".." in parts:
                    return findings + [Finding(
                        code="PYTHON-DIST-003",
                        message=f"Wheel '{rel_newest}' contains unsafe member path '{info.filename}'.",
                        path=rel_newest,
                        remediation="Rebuild wheel with canonical relative member paths.",
                    )]
                total_uncompressed += max(0, info.file_size)
                if total_uncompressed > _MAX_WHEEL_UNCOMPRESSED_BYTES:
                    return findings + [Finding(
                        code="PYTHON-DIST-003",
                        message=f"Wheel '{rel_newest}' uncompressed payload exceeds {_MAX_WHEEL_UNCOMPRESSED_BYTES} bytes.",
                        path=rel_newest,
                        remediation="Rebuild clean wheel within size bounds.",
                    )]
                if norm_name.endswith(".py") and not parts[0].endswith((".dist-info", ".data")):
                    wheel_py_files["/".join(parts)] = zf.read(info.filename)

            wheel_ver = _extract_wheel_version(newest_wheel.name, zf)
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        return findings + [Finding(
            code="PYTHON-DIST-003",
            message=f"Corrupt or unreadable wheel '{rel_newest}': {exc}",
            path=rel_newest,
            remediation="Rebuild wheel with `python -m build --wheel`.",
        )]

    if declared_version and wheel_ver and wheel_ver != declared_version:
        findings.append(Finding(
            code="PYTHON-DIST-001",
            message=(
                f"version_mismatch: newest wheel '{rel_newest}' has version '{wheel_ver}', "
                f"expected source version '{declared_version}'."
            ),
            path=rel_newest,
            remediation="Rebuild dist/ wheel (`python -m build --wheel`) or remove stale artifacts before release.",
        ))

    for pkg_name, pkg_dir in packages:
        for src_py in sorted(pkg_dir.rglob("*.py")):
            rel_inside_pkg = src_py.relative_to(pkg_dir)
            if any(part in _SKIP_DIRS or part.startswith(".") for part in rel_inside_pkg.parts):
                continue
            rel_src = str(src_py.relative_to(root))
            src_bytes, err = _read_bounded_bytes(root, src_py)
            if err is not None or src_bytes is None:
                findings.append(Finding(
                    code="PYTHON-DIST-003",
                    message=f"Cannot read source module '{rel_src}' for wheel parity check: {err}",
                    path=rel_src,
                    remediation="Ensure all package source modules are regular bounded files.",
                ))
                continue
            wheel_key = f"{pkg_name}/{rel_inside_pkg.as_posix()}"
            if wheel_key not in wheel_py_files:
                findings.append(Finding(
                    code="PYTHON-DIST-003",
                    message=f"build_file_missing: source module '{rel_src}' is absent from '{rel_newest}'.",
                    path=rel_src,
                    remediation="Rebuild wheel (`python -m build --wheel`) so all source modules are packaged.",
                ))
            elif wheel_py_files[wheel_key] != src_bytes:
                findings.append(Finding(
                    code="PYTHON-DIST-001",
                    message=f"build_content_differs: '{rel_src}' differs byte-for-byte from packaged '{wheel_key}' in '{rel_newest}'.",
                    path=rel_src,
                    remediation="Rebuild wheel (`python -m build --wheel`) so dist/ matches the source commit byte-for-byte.",
                ))
    return findings


def check_python_pack(root: Path) -> List[Finding]:
    """Run S1 static conformance checks for wellmanifest/python."""
    root = root.resolve()
    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.exists():
        return [Finding(
            code="PYTHON-DIST-001",
            message="Repository adopting 'wellmanifest/python' is missing pyproject.toml.",
            path="pyproject.toml",
            remediation="Create pyproject.toml declaring [project] metadata and build-system.",
        )]

    doc, load_findings = _load_pyproject(root, pyproject_path)
    if load_findings or doc is None:
        return load_findings

    findings: List[Finding] = []
    project = doc.get("project") if isinstance(doc.get("project"), dict) else {}
    poetry = (
        doc.get("tool", {}).get("poetry", {})
        if isinstance(doc.get("tool"), dict) and isinstance(doc.get("tool", {}).get("poetry"), dict)
        else {}
    )
    pyproject_version = project.get("version") or poetry.get("version")
    declared_version = pyproject_version.strip() if isinstance(pyproject_version, str) and pyproject_version.strip() else None

    version_path = root / "VERSION"
    if version_path.exists():
        ver_raw, ver_err = _read_bounded_bytes(root, version_path)
        if ver_err is not None or ver_raw is None:
            findings.append(Finding(
                code="PYTHON-DIST-001",
                message=f"Cannot read VERSION safely: {ver_err}",
                path="VERSION",
                remediation="Ensure VERSION is a regular UTF-8 file.",
            ))
        else:
            file_version = ver_raw.decode("utf-8", errors="replace").strip()
            if declared_version and file_version and declared_version != file_version:
                findings.append(Finding(
                    code="PYTHON-DIST-001",
                    message=(
                        f"version_mismatch: pyproject.toml version '{declared_version}' "
                        f"differs from VERSION '{file_version}'."
                    ),
                    path="pyproject.toml",
                    remediation="Synchronize pyproject.toml and VERSION before building or releasing.",
                ))
            declared_version = file_version or declared_version

    if not declared_version and "version" not in (project.get("dynamic") or []):
        findings.append(Finding(
            code="PYTHON-DIST-001",
            message="pyproject.toml does not declare a package version.",
            path="pyproject.toml",
            remediation="Declare [project].version in pyproject.toml (and keep it synchronized with VERSION).",
        ))

    findings.extend(_check_cli_scripts(root, doc))
    packages = _discover_source_packages(root, doc)
    findings.extend(_check_dist_wheels(root, declared_version, packages))
    return findings
