"""Tests for wellmanifest/session-recovery standard conformance and uncrash diagnostics."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from wellman.runner import ConformanceRunner
from wellman.validator import Finding


def test_session_recovery_healthy(tmp_path: Path):
    """Test that healthy session storage produces no findings."""
    fake_home = tmp_path / "home"
    agy_root = fake_home / ".gemini" / "antigravity-cli"
    conv_dir = agy_root / "conversations"
    conv_dir.mkdir(parents=True)

    # Create a valid SQLite DB
    db_path = conv_dir / "test-session-1234.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE metadata (key TEXT, val TEXT);")
    conn.execute("INSERT INTO metadata VALUES ('title', 'Test');")
    conn.commit()
    conn.close()

    runner = ConformanceRunner(tmp_path)
    findings = runner.check_session_recovery(home=fake_home)
    assert len(findings) == 0


def test_session_recovery_detects_corrupted_db(tmp_path: Path):
    """Test detection of corrupted SQLite session databases (GOV-SESSION-RECOVERY-001)."""
    fake_home = tmp_path / "home"
    agy_root = fake_home / ".gemini" / "antigravity-cli"
    conv_dir = agy_root / "conversations"
    conv_dir.mkdir(parents=True)

    # Create a corrupt SQLite file
    db_path = conv_dir / "corrupted-session-5678.db"
    db_path.write_bytes(b"SQLite format 3\x00garbage-corrupted-bytes-padding" * 10)

    runner = ConformanceRunner(tmp_path)
    findings = runner.check_session_recovery(home=fake_home)

    corrupted_findings = [f for f in findings if f.code == "GOV-SESSION-RECOVERY-001"]
    assert len(corrupted_findings) >= 1
    assert "corrupted-session-5678" in corrupted_findings[0].message
    assert corrupted_findings[0].severity == "ERROR"


def test_session_recovery_detects_panic_log(tmp_path: Path):
    """Test detection of agent panics in logs (GOV-SESSION-RECOVERY-002)."""
    fake_home = tmp_path / "home"
    agy_root = fake_home / ".gemini" / "antigravity-cli"
    log_dir = agy_root / "log"
    log_dir.mkdir(parents=True)

    log_file = log_dir / "agent-crash.log"
    log_file.write_text(
        "2026-10-10 12:00:00 [ERROR] program was killed: program experienced a panic\n"
        "runtime error: invalid memory address or nil pointer dereference\n"
    )

    runner = ConformanceRunner(tmp_path)
    findings = runner.check_session_recovery(home=fake_home)

    panic_findings = [f for f in findings if f.code == "GOV-SESSION-RECOVERY-002"]
    assert len(panic_findings) >= 1
    assert panic_findings[0].severity == "WARNING"
    assert "agent-crash.log" in panic_findings[0].message


def test_session_recovery_adoption_lock_check(tmp_path: Path):
    """Test warning when wellmanifest/session-recovery is adopted without lockfile."""
    gov_dir = tmp_path / ".governance"
    gov_dir.mkdir(parents=True)
    manifest = gov_dir / "manifest.json"
    manifest.write_text(
        json.dumps({
            "schema": "new-project.manifest/v1",
            "packs": ["wellmanifest/session-recovery"],
        })
    )

    empty_home = tmp_path / "empty_home"
    empty_home.mkdir()

    runner = ConformanceRunner(tmp_path)
    findings = runner.check_session_recovery(home=empty_home)

    lock_findings = [f for f in findings if f.code == "GOV-SESSION-RECOVERY-LOCK"]
    assert len(lock_findings) == 1
    assert "session-recovery.lock.json" in lock_findings[0].message


def test_run_standard_session_recovery(tmp_path: Path):
    """Test running standard conformance check via run_standard."""
    runner = ConformanceRunner(tmp_path)
    findings = runner.run_standard("wellmanifest/session-recovery")
    assert isinstance(findings, list)
