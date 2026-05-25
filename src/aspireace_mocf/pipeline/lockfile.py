"""Lockfile — prevent concurrent runs against the same run_id.

Purpose: if a teacher accidentally launches two factory runs with the same
run_id (e.g. from two terminal windows or from cron + manual), they will
trample each other's files. This module provides a context-manager-style lock
that fails fast if another process already holds the lock.

The lock is a sentinel file at `runs/<run_id>/.lock` containing the PID +
hostname + timestamp of the holder. Stale locks (PID no longer running) are
forcibly broken with a warning.

Owner: ATRIYA / AspireACE Factory
Version: 1.0.0 (M1)
"""
from __future__ import annotations

import json
import os
import socket
import time
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aspireace_mocf.utils.errors import PipelineError, PipelineErrorCode
from aspireace_mocf.utils.logging import get_logger


_log = get_logger(__name__)


def _pid_alive(pid: int) -> bool:
    """Return True if the given PID is still running on this machine.

    Windows fallback: assume any PID we can read is alive (no os.kill(0) on
    Windows that doesn't actually signal). Conservative: don't auto-break locks
    on Windows.
    """
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            # Best-effort on Windows. Don't auto-break locks.
            return True
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return True  # err on the side of "alive"


class RunLock(AbstractContextManager):
    """Filesystem lock scoped to a run_id.

    Usage:
        with RunLock(run_id):
            ... pipeline code ...

    On entry, raises PipelineError(LOCKFILE_HELD_BY_OTHER_RUN) if another
    process holds the lock and that process is still alive.

    On exit, releases the lock.
    """

    def __init__(self, run_id: str, base_dir: Path | str = "runs"):
        self.run_id = run_id
        self.lock_path = Path(base_dir) / run_id / ".lock"

    def __enter__(self) -> "RunLock":
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_path.exists():
            try:
                existing = json.loads(self.lock_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                _log.warning("lockfile_unreadable_breaking", path=str(self.lock_path), error=str(exc))
                self.lock_path.unlink()
                existing = None
            if existing is not None:
                if existing.get("hostname") == socket.gethostname() and _pid_alive(existing.get("pid", 0)):
                    raise PipelineError(
                        code=PipelineErrorCode.LOCKFILE_HELD_BY_OTHER_RUN,
                        message=(
                            f"Another process (pid={existing.get('pid')}, "
                            f"started={existing.get('acquired_at_utc')}) is already "
                            f"running run_id={self.run_id!r}. If that process is dead, "
                            f"delete {self.lock_path} manually."
                        ),
                    )
                _log.warning(
                    "stale_lockfile_breaking",
                    path=str(self.lock_path),
                    stale_holder=existing,
                )
                self.lock_path.unlink()
        self._write_lock()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            if self.lock_path.exists():
                self.lock_path.unlink()
        except OSError as exc:
            _log.warning("lockfile_release_failed", path=str(self.lock_path), error=str(exc))

    def _write_lock(self) -> None:
        payload = {
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "run_id": self.run_id,
            "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
            "acquired_at_unix": time.time(),
        }
        self.lock_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        _log.info("lockfile_acquired", path=str(self.lock_path), **payload)
