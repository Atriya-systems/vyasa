"""Tests for pipeline/lockfile.py — concurrent-run protection."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from aspireace_mocf.pipeline.lockfile import RunLock
from aspireace_mocf.utils.errors import PipelineError, PipelineErrorCode


def test_lock_acquired_writes_lockfile(tmp_path):
    with RunLock("test_run_001", base_dir=tmp_path):
        lock_path = tmp_path / "test_run_001" / ".lock"
        assert lock_path.exists()
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        assert payload["pid"] == os.getpid()
        assert payload["run_id"] == "test_run_001"
        assert "acquired_at_utc" in payload


def test_lock_released_on_exit(tmp_path):
    with RunLock("test_run_002", base_dir=tmp_path):
        pass
    lock_path = tmp_path / "test_run_002" / ".lock"
    assert not lock_path.exists()


def test_lock_released_on_exception(tmp_path):
    lock_path = tmp_path / "test_run_003" / ".lock"
    with pytest.raises(ValueError):
        with RunLock("test_run_003", base_dir=tmp_path):
            raise ValueError("simulated failure")
    # Lock should still be released.
    assert not lock_path.exists()


@pytest.mark.skipif(os.name == "nt", reason="Stale PID detection differs on Windows.")
def test_stale_lock_with_dead_pid_is_broken(tmp_path):
    """A lockfile from a PID that is no longer alive should be auto-cleaned."""
    lock_dir = tmp_path / "test_run_004"
    lock_dir.mkdir(parents=True)
    lock_path = lock_dir / ".lock"
    # Write a fake lock claiming PID 99999 (very unlikely to be alive).
    import socket
    lock_path.write_text(json.dumps({
        "pid": 99999,
        "hostname": socket.gethostname(),
        "run_id": "test_run_004",
        "acquired_at_utc": "2026-01-01T00:00:00+00:00",
        "acquired_at_unix": 1735689600.0,
    }), encoding="utf-8")

    # Should NOT raise; should break the stale lock and acquire fresh.
    with RunLock("test_run_004", base_dir=tmp_path):
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        assert payload["pid"] == os.getpid()


def test_corrupt_lockfile_is_broken(tmp_path):
    """A lockfile with invalid JSON content should be broken."""
    lock_dir = tmp_path / "test_run_005"
    lock_dir.mkdir(parents=True)
    lock_path = lock_dir / ".lock"
    lock_path.write_text("not valid json {{{", encoding="utf-8")

    # Should NOT raise; should break the corrupt lock and acquire fresh.
    with RunLock("test_run_005", base_dir=tmp_path):
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        assert payload["pid"] == os.getpid()


def test_live_lock_prevents_second_acquire(tmp_path):
    """A lockfile from an alive PID on the same host blocks a second acquire."""
    lock_dir = tmp_path / "test_run_006"
    lock_dir.mkdir(parents=True)
    lock_path = lock_dir / ".lock"
    import socket
    # Write a lock claiming THIS pid + this host. It's "alive" (we are it).
    lock_path.write_text(json.dumps({
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "run_id": "test_run_006",
        "acquired_at_utc": "2026-01-01T00:00:00+00:00",
        "acquired_at_unix": 1735689600.0,
    }), encoding="utf-8")

    with pytest.raises(PipelineError) as exc_info:
        with RunLock("test_run_006", base_dir=tmp_path):
            pass
    assert exc_info.value.code == PipelineErrorCode.LOCKFILE_HELD_BY_OTHER_RUN
