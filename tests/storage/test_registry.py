"""Tests for asynchronous batched RegistryWriter."""

import concurrent.futures
from pathlib import Path

import pytest

from storage.office_db import OfficeDB
from storage.registry import (
    CliCommandRecord,
    LlmCallRecord,
    RegistryWriter,
    ToolCallRecord,
)


@pytest.fixture
def db(tmp_path: Path) -> OfficeDB:
    db_path = tmp_path / "test_registry.db"
    office_db = OfficeDB(db_path)
    yield office_db
    office_db.close()


def test_registry_writer_flushes_batches(db: OfficeDB) -> None:
    with RegistryWriter(db, batch_size=2, flush_interval=0.05) as writer:
        writer.enqueue(
            LlmCallRecord(
                agent="pm",
                model="gpt-4o",
                tokens_in=100,
                tokens_out=50,
                cost=0.002,
                duration_ms=450,
                prompt_text="System instructions...",
                response_text="Decision: accept",
            )
        )
        writer.enqueue(
            ToolCallRecord(
                agent="technical",
                tool="get_indicators",
                params={"symbol": "AAPL"},
                result={"atr": 2.5},
            )
        )
        writer.enqueue(
            CliCommandRecord(
                command="task",
                args={"ticker": "AAPL"},
            )
        )
        writer.flush()

    # Verify persisted rows
    llm_count = db.connection.execute("SELECT count(*) FROM llm_calls").fetchone()[0]
    assert llm_count == 1

    tool_count = db.connection.execute("SELECT count(*) FROM tool_calls").fetchone()[0]
    assert tool_count == 1

    cli_count = db.connection.execute("SELECT count(*) FROM cli_commands").fetchone()[0]
    assert cli_count == 1


def test_registry_writer_deduplicates_repeated_prompts(db: OfficeDB) -> None:
    repeated_system_prompt = "You are a professional financial agent."
    with RegistryWriter(db, batch_size=5, flush_interval=0.05) as writer:
        for i in range(5):
            writer.enqueue(
                LlmCallRecord(
                    agent="pm",
                    model="gpt-4o",
                    prompt_text=repeated_system_prompt,
                    response_text=f"Response {i}",
                )
            )
        writer.flush()

    # 5 llm calls logged
    llm_calls = db.connection.execute("SELECT prompt_blob FROM llm_calls").fetchall()
    assert len(llm_calls) == 5
    first_hash = llm_calls[0]["prompt_blob"]
    assert all(row["prompt_blob"] == first_hash for row in llm_calls)

    # Blobs table deduplicates by hash: only 1 entry for the prompt
    blob_count = db.connection.execute("SELECT count(*) FROM blobs WHERE hash = ?", (first_hash,)).fetchone()[0]
    assert blob_count == 1


def test_registry_bounded_queue_drops_oldest(db: OfficeDB) -> None:
    # Set max_queue_size to 3
    # Don't let background thread drain by setting large flush_interval and not flushing until queue fills
    with RegistryWriter(db, batch_size=10, flush_interval=10.0, max_queue_size=3) as writer:
        for i in range(6):
            writer.enqueue(CliCommandRecord(command=f"cmd_{i}"))

        assert writer.dropped_count == 3
        assert writer.queue_size == 3

        writer.flush()

    # Remaining in DB should be cmd_3, cmd_4, cmd_5
    rows = db.connection.execute("SELECT command FROM cli_commands ORDER BY id ASC").fetchall()
    commands = [r["command"] for r in rows]
    assert commands == ["cmd_3", "cmd_4", "cmd_5"]


def test_registry_writer_concurrent_enqueue(db: OfficeDB) -> None:
    with RegistryWriter(db, batch_size=20, flush_interval=0.05, max_queue_size=1000) as writer:
        def worker(thread_idx: int) -> None:
            for i in range(10):
                writer.enqueue(
                    ToolCallRecord(
                        agent=f"agent_{thread_idx}",
                        tool="fetch",
                        params={"i": i},
                    )
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, idx) for idx in range(5)]
            concurrent.futures.wait(futures)

        writer.flush()

    tool_count = db.connection.execute("SELECT count(*) FROM tool_calls").fetchone()[0]
    assert tool_count == 50
    assert writer.dropped_count == 0


def test_registry_writer_parameter_validation(db: OfficeDB) -> None:
    with pytest.raises(ValueError):
        RegistryWriter(db, batch_size=0)
    with pytest.raises(ValueError):
        RegistryWriter(db, flush_interval=0.0)
    with pytest.raises(ValueError):
        RegistryWriter(db, max_queue_size=0)

