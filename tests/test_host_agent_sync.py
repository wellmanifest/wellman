"""Tests for version-stamped WellManifest standards SSOT host sync."""
from __future__ import annotations

import subprocess
from pathlib import Path

from wellman.host_agent_sync import (
    main as sync_hosts_main,
    maybe_auto_sync_host_agents,
    read_synced_version,
    sync_host_agents,
)


def _setup_fake_host(tmp_path: Path) -> tuple[Path, Path, Path]:
    home = tmp_path / "home"
    ws = home / "github"
    wm = ws / "wellmanifest"
    wm.mkdir(parents=True)

    # Create a small repos.manifest + one local standard checkout
    (wm / "worktrees").mkdir()
    (wm / "worktrees" / "README.md").write_text(
        "# Worktrees\n\nCanonical delivery worktree placement standard.\n",
        encoding="utf-8",
    )
    (wm / "repos.manifest").write_text(
        "# inventory\n"
        "worktrees\tgit@github.com:wellmanifest/worktrees.git\tpublic\tyes\tcheckout\n"
        "custom-std\tgit@github.com:wellmanifest/custom-std.git\tpublic\tno\tmissing\tcustom standard note\n",
        encoding="utf-8",
    )

    # Create non-git workspace & org AGENTS.md + all LLM host dirs
    (ws / "AGENTS.md").write_text("# Root AGENTS\n", encoding="utf-8")
    (wm / "AGENTS.md").write_text("# WellManifest AGENTS\n", encoding="utf-8")
    (ws / "subactor").mkdir()
    (ws / "subactor" / "AGENTS.md").write_text("# Subactor AGENTS\n", encoding="utf-8")

    # Create a git-tracked org dir that MUST be skipped
    git_org = ws / "tracked-org"
    git_org.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=git_org, check=True)
    (git_org / "AGENTS.md").write_text("# Tracked git AGENTS\n", encoding="utf-8")

    # LLM host config directories
    for rel in (
        ".claude",
        ".codex",
        ".codex-softreck",
        ".gemini",
        ".cursor/rules",
        ".config/opencode",
        ".codeium/windsurf/memories",
        ".copilot",
        ".factory",
        ".continue",
        ".cline",
        ".aider",
    ):
        (home / rel).mkdir(parents=True, exist_ok=True)

    # Existing Windsurf rule must be preserved when appending managed block
    (home / ".codeium" / "windsurf" / "memories" / "global_rules.md").write_text(
        "# Existing Windsurf Rule\nKeep me intact.\n",
        encoding="utf-8",
    )
    return home, ws, wm


def test_sync_host_agents_writes_index_invariants_and_all_hosts(tmp_path: Path) -> None:
    home, ws, wm = _setup_fake_host(tmp_path)

    res = sync_host_agents(home=home, workspace_root=ws, wellmanifest_root=wm, version="0.23.3")
    assert res["status"] == "synced"
    assert res["version"] == "0.23.3"
    assert res["standards_count"] >= 2

    standards_text = (wm / "STANDARDS.md").read_text(encoding="utf-8")
    assert "**worktrees**" in standards_text
    assert "**wellmanifest/worktrees**" not in standards_text
    assert "wellmanifest/wellmanifest/" not in standards_text
    assert "**custom-std**" in standards_text
    assert "NEVER" in standards_text and ".worktrees/ticket-NNN--description" in standards_text

    # Existing Windsurf rule preserved + SSOT block appended
    windsurf_text = (home / ".codeium" / "windsurf" / "memories" / "global_rules.md").read_text(encoding="utf-8")
    assert "Keep me intact." in windsurf_text
    assert "wellman-version=0.23.3" in windsurf_text

    # All other LLM host files created/updated
    assert (home / ".claude" / "CLAUDE.md").is_file()
    assert (home / ".codex" / "AGENTS.md").is_file()
    assert (home / ".codex-softreck" / "AGENTS.md").is_file()
    assert (home / ".gemini" / "GEMINI.md").is_file()
    assert (home / ".config" / "opencode" / "AGENTS.md").is_file()
    assert (home / ".copilot" / "copilot-instructions.md").is_file()
    assert (home / ".factory" / "AGENTS.md").is_file()
    assert (home / ".continue" / "rules" / "wellmanifest-standards-ssot.md").is_file()
    assert (home / "Documents" / "Cline" / "Rules" / "wellmanifest-standards-ssot.md").is_file()
    assert (home / ".cursor" / "rules" / "wellmanifest-standards-ssot.mdc").is_file()
    assert str(wm / "AGENT-INVARIANTS.md") in (home / ".aider.conf.yml").read_text(encoding="utf-8")

    # Git-tracked directory was NOT modified
    tracked_key = str(ws / "tracked-org" / "AGENTS.md")
    assert res["targets"][tracked_key] == "SKIP_GIT"
    assert (ws / "tracked-org" / "AGENTS.md").read_text(encoding="utf-8") == "# Tracked git AGENTS\n"


def test_if_version_changed_skips_same_version_and_resyncs_on_bump(tmp_path: Path) -> None:
    home, ws, wm = _setup_fake_host(tmp_path)

    first = sync_host_agents(home=home, workspace_root=ws, wellmanifest_root=wm, version="0.23.3")
    assert first["status"] == "synced"
    assert read_synced_version(ws / "AGENTS.md") == "0.23.3"

    # Same version -> fast no-op
    second = sync_host_agents(
        home=home, workspace_root=ws, wellmanifest_root=wm, version="0.23.3", if_version_changed=True
    )
    assert second["status"] == "up_to_date"
    assert second["skipped"] is True

    # New wellman version -> automatic re-sync updates embedded stamp
    third = sync_host_agents(
        home=home, workspace_root=ws, wellmanifest_root=wm, version="0.24.0", if_version_changed=True
    )
    assert third["status"] == "synced"
    assert third["skipped"] is False
    assert third["previous_version"] == "0.23.3"
    assert read_synced_version(ws / "AGENTS.md") == "0.24.0"
    assert read_synced_version(home / ".claude" / "CLAUDE.md") == "0.24.0"


def test_check_only_reports_drift_without_mutating_files(tmp_path: Path) -> None:
    home, ws, wm = _setup_fake_host(tmp_path)

    rc = sync_hosts_main([
        "--home", str(home),
        "--workspace-root", str(ws),
        "--wellmanifest-root", str(wm),
        "--check",
        "--json",
    ])
    assert rc == 2
    assert not (wm / "STANDARDS.md").exists()
    assert not (home / ".config" / "opencode" / "AGENTS.md").exists()

    rc_apply = sync_hosts_main([
        "--home", str(home),
        "--workspace-root", str(ws),
        "--wellmanifest-root", str(wm),
    ])
    assert rc_apply == 0

    rc_clean = sync_hosts_main([
        "--home", str(home),
        "--workspace-root", str(ws),
        "--wellmanifest-root", str(wm),
        "--check",
    ])
    assert rc_clean == 0


def test_maybe_auto_sync_respects_ci_guards_and_triggers_on_version_bump(tmp_path: Path) -> None:
    home, ws, wm = _setup_fake_host(tmp_path)

    # Skips in CI / pytest / opt-out env
    assert maybe_auto_sync_host_agents(home=home, workspace_root=ws, wellmanifest_root=wm, version="0.23.3", env={"CI": "true"}) is None
    assert maybe_auto_sync_host_agents(home=home, workspace_root=ws, wellmanifest_root=wm, version="0.23.3", env={"WELLMAN_NO_AUTO_HOST_SYNC": "1"}) is None
    assert not (wm / "STANDARDS.md").exists()

    # Clean host env -> auto-syncs on first run
    first = maybe_auto_sync_host_agents(home=home, workspace_root=ws, wellmanifest_root=wm, version="0.23.3", env={})
    assert first is not None and first["status"] == "synced"
    assert read_synced_version(ws / "AGENTS.md") == "0.23.3"

    # Same version -> fast skipped no-op
    second = maybe_auto_sync_host_agents(home=home, workspace_root=ws, wellmanifest_root=wm, version="0.23.3", env={})
    assert second is not None and second["skipped"] is True

    # New wellman version -> automatically updates all host configs
    third = maybe_auto_sync_host_agents(home=home, workspace_root=ws, wellmanifest_root=wm, version="0.24.0", env={})
    assert third is not None and third["status"] == "synced" and third["skipped"] is False
    assert read_synced_version(ws / "AGENTS.md") == "0.24.0"
    assert read_synced_version(home / ".config" / "opencode" / "AGENTS.md") == "0.24.0"


def test_ssot_block_placed_at_top_right_after_h1_even_in_large_agents_md(tmp_path: Path) -> None:
    home, ws, wm = _setup_fake_host(tmp_path)
    long_prose = "# Workspace Root\n\n" + ("Legacy policy paragraph.\n" * 300)
    (ws / "AGENTS.md").write_text(
        long_prose + "\n<!-- wellmanifest:standards-ssot:start -->\nold\n<!-- wellmanifest:standards-ssot:end -->\n",
        encoding="utf-8",
    )

    res = sync_host_agents(home=home, workspace_root=ws, wellmanifest_root=wm, version="0.23.3")
    assert res["status"] == "synced"
    updated = (ws / "AGENTS.md").read_text(encoding="utf-8")
    assert updated.startswith("# Workspace Root\n\n<!-- wellmanifest:standards-ssot:start wellman-version=0.23.3 -->")
    assert updated.find("wellmanifest:standards-ssot:start") < 100
    assert updated.count("wellmanifest:standards-ssot:start") == 1
    assert "Legacy policy paragraph." in updated
