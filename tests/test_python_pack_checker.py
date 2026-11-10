"""Unit tests for the S1 static conformance checker of wellmanifest/python."""

from __future__ import annotations

from pathlib import Path
import zipfile

from wellman.python_pack_checker import check_python_pack
from wellman.runner import ConformanceRunner


def _make_wheel(
    wheel_path: Path,
    *,
    pkg_name: str = "demo_pkg",
    version: str = "1.2.3",
    files: dict[str, bytes],
) -> None:
    wheel_path.parent.mkdir(parents=True, exist_ok=True)
    dist_info = f"{pkg_name}-{version}.dist-info"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr(f"{dist_info}/METADATA", f"Metadata-Version: 2.1\nName: {pkg_name}\nVersion: {version}\n")
        for rel_path, content in files.items():
            zf.writestr(rel_path, content)


def test_python_pack_passes_clean_package_with_matching_wheel(tmp_path: Path) -> None:
    (tmp_path / "VERSION").write_text("1.2.3\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo-pkg"\nversion = "1.2.3"\n\n[project.scripts]\ndemo = "demo_pkg.cli:main"\n',
        encoding="utf-8",
    )
    pkg = tmp_path / "src" / "demo_pkg"
    pkg.mkdir(parents=True)
    init_bytes = b'"""Demo package."""\n__version__ = "1.2.3"\n'
    cli_bytes = (
        b"import argparse\n"
        b"def main():\n"
        b"    p = argparse.ArgumentParser()\n"
        b'    p.add_argument("--version", action="store_true")\n'
    )
    (pkg / "__init__.py").write_bytes(init_bytes)
    (pkg / "cli.py").write_bytes(cli_bytes)

    _make_wheel(
        tmp_path / "dist" / "demo_pkg-1.2.3-py3-none-any.whl",
        pkg_name="demo_pkg",
        version="1.2.3",
        files={
            "demo_pkg/__init__.py": init_bytes,
            "demo_pkg/cli.py": cli_bytes,
        },
    )

    findings = ConformanceRunner(tmp_path).run_standard("wellmanifest/python")
    assert findings == []


def test_python_pack_detects_pyproject_and_version_mismatch(tmp_path: Path) -> None:
    (tmp_path / "VERSION").write_text("1.2.4\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo-pkg"\nversion = "1.2.3"\n', encoding="utf-8")

    findings = check_python_pack(tmp_path)
    assert any(f.code == "PYTHON-DIST-001" and "version_mismatch" in f.message for f in findings)


def test_python_pack_detects_wheel_content_drift_and_missing_module(tmp_path: Path) -> None:
    (tmp_path / "VERSION").write_text("1.2.3\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo-pkg"\nversion = "1.2.3"\n', encoding="utf-8")
    pkg = tmp_path / "src" / "demo_pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_bytes(b"X = 2\n")
    (pkg / "extra.py").write_bytes(b"Y = 3\n")

    _make_wheel(
        tmp_path / "dist" / "demo_pkg-1.2.3-py3-none-any.whl",
        pkg_name="demo_pkg",
        version="1.2.3",
        files={"demo_pkg/__init__.py": b"X = 1\n"},
    )

    findings = check_python_pack(tmp_path)
    codes_msgs = [(f.code, f.message) for f in findings]
    assert any(code == "PYTHON-DIST-001" and "build_content_differs" in msg for code, msg in codes_msgs)
    assert any(code == "PYTHON-DIST-003" and "build_file_missing" in msg for code, msg in codes_msgs)


def test_python_pack_detects_broken_entrypoint_and_missing_version_flag(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo-pkg"\nversion = "0.1.0"\n\n'
        '[project.scripts]\nmissing_mod = "demo_pkg.missing:run"\nno_ver = "demo_pkg.cli:run"\n',
        encoding="utf-8",
    )
    pkg = tmp_path / "src" / "demo_pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_bytes(b"")
    (pkg / "cli.py").write_bytes(b"def run():\n    return 0\n")

    findings = check_python_pack(tmp_path)
    errors = [f for f in findings if f.severity == "ERROR"]
    warnings = [f for f in findings if f.severity == "WARNING"]
    assert any(f.code == "PYTHON-DIST-002" and "missing_mod" in f.message for f in errors)
    assert any(f.code == "PYTHON-DIST-002" and "--version" in f.message for f in warnings)


def test_python_pack_rejects_unsafe_wheel_member_paths_and_symlinks(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo-pkg"\nversion = "0.1.0"\n', encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    bad_whl = dist / "demo_pkg-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(bad_whl, "w") as zf:
        zf.writestr("../escape.py", "Evil = 1\n")

    findings = check_python_pack(tmp_path)
    assert any(f.code == "PYTHON-DIST-003" and "unsafe member path" in f.message for f in findings)

    outside = tmp_path.parent / "outside_pyproject.toml"
    outside.write_text('[project]\nname = "x"\nversion = "0.1.0"\n', encoding="utf-8")
    (tmp_path / "pyproject.toml").unlink()
    (tmp_path / "pyproject.toml").symlink_to(outside)
    sym_findings = check_python_pack(tmp_path)
    assert any(f.code == "PYTHON-DIST-001" and "symlink" in f.message for f in sym_findings)
