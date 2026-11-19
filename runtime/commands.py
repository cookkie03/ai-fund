"""Pydantic models for Runtime commands and results."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CommandResult(BaseModel):
    ok: bool = True
    data: dict[str, Any] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)


class EnqueueTask(BaseModel):
    agent: str
    ticker: str
    reason: str
    when_ts: str | None = None


class Say(BaseModel):
    agent: str
    chat: str
    text: str


class AddWatchlist(BaseModel):
    ticker: str
    note: str | None = None


class RemoveWatchlist(BaseModel):
    ticker: str


class ApproveOrder(BaseModel):
    order_id: int
    confirm: Literal[True]


class RejectOrder(BaseModel):
    order_id: int
    reason: str


class Halt(BaseModel):
    cancel_open: bool = True
    confirm: Literal[True]


class Resume(BaseModel):
    confirm: Literal[True]


class ReconcileBroker(BaseModel):
    pass


class RefreshData(BaseModel):
    kinds: list[str] | None = None
    force: bool = False


class MarkInboxRead(BaseModel):
    item_id: int


class IngestAlert(BaseModel):
    ticker: str
    source: str
    reason: str
    data: dict[str, Any] = Field(default_factory=dict)
