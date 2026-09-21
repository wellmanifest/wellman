"""Tests for safe repository-fleet discovery and adoption."""

import json
import subprocess

from wellman import __version__
from wellman.fleet import apply_plan, build_plan, discover_repositories


def make_repository(parent, name, remote="git@github.com:acme/example.git"):
    path = parent / name
    path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "remote", "add", "origin", remote], cwd=path, check=True)
    return path


def test_discover_skips_hidden_git_directories(tmp_path):
    make_repository(tmp_path, "visible", "git@github.com:acme/visible.git")
    make_repository(tmp_path, ".hidden", "git@github.com:acme/hidden.git")

    assert discover_repositories(tmp_path) == [tmp_path / "visible"]


def test_fleet_plan_blocks_dirty_repository(tmp_path):
    repo = make_repository(tmp_path, "visible")
    (repo / "README.md").write_text("dirty\n", encoding="utf-8")

    plan = build_plan(tmp_path, "baseline")

    assert plan["blocked"] == 1
    assert plan["repositories"][0]["ready"] is False
    assert "working tree is dirty" in plan["repositories"][0]["blockers"]


def test_fleet_apply_creates_repository_bound_adoption(tmp_path):
    repo = make_repository(tmp_path, "visible", "https://github.com/acme/visible.git")
    plan = build_plan(tmp_path, "baseline")

    result = apply_plan(plan, "baseline")

    assert result["repositories"][0]["status"] == "updated"
    manifest = json.loads((repo / ".governance/manifest.json").read_text(encoding="utf-8"))
    docs = json.loads((repo / ".governance/docs.json").read_text(encoding="utf-8"))
    assert manifest["standard"] == {"id": "profile:baseline", "version": __version__}
    assert docs["repository"] == "acme/visible"


def test_fleet_manifest_update_preserves_custom_fields(tmp_path):
    repo = make_repository(tmp_path, "visible")
    gov = repo / ".governance"
    gov.mkdir()
    (gov / "manifest.json").write_text(
        json.dumps({
            "schema": "new-project.governance/v2",
            "standard": {"id": "wellmanifest/new-project", "version": "0.20.32"},
            "custom": {"keep": True},
        }),
        encoding="utf-8",
    )

    plan = build_plan(tmp_path, "baseline", allow_dirty=True, update_manifests=True)
    apply_plan(plan, "baseline", update_manifests=True)
    updated = json.loads((gov / "manifest.json").read_text(encoding="utf-8"))

    assert updated["standard"]["version"] == __version__
    assert updated["custom"] == {"keep": True}
