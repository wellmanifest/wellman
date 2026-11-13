"""Unit tests for .subactor/cache/ exclusion in bundled governance_check.changed_paths."""
from __future__ import annotations

import json
from pathlib import Path
from wellman._bundled.governance_check import changed_paths, coordination_policy_valid


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


def test_bundled_checker_accepts_closed_idle_takeover_policy() -> None:
    manifest_path = Path(__file__).resolve().parents[1] / ".governance/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    coordination = {
        **manifest["coordination"],
        "idleTakeover": {"enabled": True, "idleMinutes": 15, "leaseMinutes": 120},
    }

    assert coordination_policy_valid(coordination)

    invalid_policies = (
        {"enabled": True, "idleMinutes": 4, "leaseMinutes": 120},
        {"enabled": True, "idleMinutes": 15, "leaseMinutes": 15},
        {"enabled": "yes", "idleMinutes": 15, "leaseMinutes": 120},
        {"enabled": True, "idleMinutes": 15, "leaseMinutes": 120, "extra": 1},
    )
    for policy in invalid_policies:
        assert not coordination_policy_valid({**manifest["coordination"], "idleTakeover": policy})


def test_bundled_checker_keeps_idle_takeover_optional_for_legacy_manifests() -> None:
    manifest_path = Path(__file__).resolve().parents[1] / ".governance/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    coordination = {key: value for key, value in manifest["coordination"].items() if key != "idleTakeover"}

    assert coordination_policy_valid(coordination)
