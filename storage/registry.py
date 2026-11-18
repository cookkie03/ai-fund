"""Registry: asynchronous batched writer for audit and operational telemetry.

Buffers LLM calls, tool calls, and CLI commands in a bounded in-memory queue
without blocking agent execution threads, flushing in batches inside single
database transactions on a background thread.
"""

from __future__ import annotations

import collections
import threading
from dataclasses import dataclass
from types import TracebackType
from typing import Self

from storage.office_db import OfficeDB


@dataclass(frozen=True)
class LlmCallRecord:
    agent: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    duration_ms: int = 0
    chat_id: int | None = None
    prompt_hash: str | None = None
    prompt_text: str | None = None
    response_text: str | None = None
    prompt_blob: str | None = None
    response_blob: str | None = None
    ts: str | None = None


@dataclass(frozen=True)
class ToolCallRecord:
    agent: str
    tool: str
    params: dict | str = "{}"
    result: dict | str = "{}"
    error: str | None = None
    chat_id: int | None = None
    ts: str | None = None


@dataclass(frozen=True)
class CliCommandRecord:
    command: str
    args: dict | str = "{}"
    ts: str | None = None


RegistryRecord = LlmCallRecord | ToolCallRecord | CliCommandRecord


class RegistryWriter:
    """Asynchronous batched telemetry writer.

    Enqueue never blocks: if the queue is full, the oldest record is dropped
    and `dropped_count` is incremented.
    """

    def __init__(
        self,
        db: OfficeDB,
        batch_size: int = 50,
        flush_interval: float = 1.0,
        max_queue_size: int = 1000,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if flush_interval <= 0:
            raise ValueError("flush_interval must be positive")
        if max_queue_size <= 0:
            raise ValueError("max_queue_size must be positive")

        self._db = db
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._max_queue_size = max_queue_size

        self._deque: collections.deque[RegistryRecord] = collections.deque()
        self._dropped_count = 0
        self._queue_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._wake_event = threading.Event()
        self._stopped = False

        self._thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="RegistryWriterThread"
        )
        self._thread.start()

    @property
    def dropped_count(self) -> int:
        with self._queue_lock:
            return self._dropped_count

    @property
    def queue_size(self) -> int:
        with self._queue_lock:
            return len(self._deque)

    def enqueue(self, record: RegistryRecord) -> None:
        """Enqueue a record without blocking. Drops oldest if full."""
        with self._queue_lock:
            if len(self._deque) >= self._max_queue_size:
                self._deque.popleft()
                self._dropped_count += 1
            self._deque.append(record)
            if len(self._deque) >= self._batch_size:
                self._wake_event.set()

    def _worker_loop(self) -> None:
        while not self._stopped:
            self._wake_event.wait(timeout=self._flush_interval)
            self._wake_event.clear()
            self._drain_and_write()

    def _drain_and_write(self) -> None:
        with self._write_lock:
            while True:
                with self._queue_lock:
                    if not self._deque:
                        break
                    batch: list[RegistryRecord] = []
                    while self._deque and len(batch) < self._batch_size:
                        batch.append(self._deque.popleft())
                if batch:
                    self._write_batch(batch)
                else:
                    break

    def _write_batch(self, batch: list[RegistryRecord]) -> None:
        if not batch:
            return
        with self._db.transaction():
            for record in batch:
                if isinstance(record, LlmCallRecord):
                    prompt_blob = record.prompt_blob
                    if record.prompt_text is not None and prompt_blob is None:
                        prompt_blob = self._db.put_blob(record.prompt_text)

                    response_blob = record.response_blob
                    if record.response_text is not None and response_blob is None:
                        response_blob = self._db.put_blob(record.response_text)

                    self._db.log_llm_call(
                        agent=record.agent,
                        model=record.model,
                        tokens_in=record.tokens_in,
                        tokens_out=record.tokens_out,
                        cost=record.cost,
                        duration_ms=record.duration_ms,
                        chat_id=record.chat_id,
                        prompt_hash=record.prompt_hash,
                        prompt_blob=prompt_blob,
                        response_blob=response_blob,
                        ts=record.ts,
                    )
                elif isinstance(record, ToolCallRecord):
                    self._db.log_tool_call(
                        agent=record.agent,
                        tool=record.tool,
                        params=record.params,
                        result=record.result,
                        error=record.error,
                        chat_id=record.chat_id,
                        ts=record.ts,
                    )
                elif isinstance(record, CliCommandRecord):
                    self._db.log_cli_command(
                        command=record.command,
                        args=record.args,
                        ts=record.ts,
                    )

    def flush(self) -> None:
        """Synchronously flush all pending records in the queue to DB."""
        self._drain_and_write()

    def close(self) -> None:
        """Stop worker thread and flush all remaining records."""
        self._stopped = True
        self._wake_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self.flush()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
