"""Test R10: Early process lock before building office/migrating DB, clean error message on collision, removal of poll interval log."""

from __future__ import annotations

import fcntl
import io
from unittest.mock import MagicMock

from interface.cli import main


def test_r10_second_runtime_refused_before_touching_db_with_clean_exit(tmp_path, monkeypatch):
    """When a lock is held, `run` exits with code != 0 and clean error, without building office."""
    db_path = tmp_path / "colliding.db"
    lock_path = db_path.with_suffix(".db.lock")

    # Acquire lock in advance as if another runtime process is running
    lock_file = open(lock_path, "w")
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    monkeypatch.setenv("TRADING_AGENT_DB", str(db_path))

    build_called = False

    def mock_factory():
        nonlocal build_called
        build_called = True
        return MagicMock()

    out = io.StringIO()
    try:
        exit_code = main(["run"], out=out, runtime_factory=mock_factory)
        # Must exit with non-zero exit code
        assert exit_code != 0
        output = out.getvalue()
        # Must contain clean error message
        assert "già attivo" in output or "already running" in output.lower()
        # Must NOT call runtime_factory or build office
        assert build_called is False
    finally:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


def test_r10_startup_output_does_not_contain_poll_interval(tmp_path, monkeypatch):
    """CLI run output must not mention poll interval."""
    db_path = tmp_path / "clean_start.db"
    monkeypatch.setenv("TRADING_AGENT_DB", str(db_path))

    mock_rt = MagicMock()
    mock_rt.office.db.path = db_path
    mock_rt.scheduler = MagicMock()

    out = io.StringIO()

    # We patch uvicorn.Server so it does not actually block
    import uvicorn

    def mock_run(self):
        self.should_exit = True

    monkeypatch.setattr(uvicorn.Server, "run", mock_run)

    _ = main(["run"], out=out, runtime_factory=lambda: mock_rt)
    output = out.getvalue()
    assert "poll interval" not in output.lower()
