"""Unit tests for .subactor/cache/ exclusion in bundled governance_check.changed_paths."""
from __future__ import annotations

from pathlib import Path
from wellman._bundled.governance_check import changed_paths


def test_changed_paths_excludes_subactor_cache_explicit(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    result = changed_paths(
        tmp_path,
        base=None,
        head="HEAD",
        explicit=[
            "src/app.py",
            ".subactor/cache/koru-verification/run-123/filter.bpf",
            "./.subactor/cache/preflight.json",
        ],
    )
    assert result == ["src/app.py"]
