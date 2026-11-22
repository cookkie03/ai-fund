"""Pydantic models for Runtime commands and results."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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
    chat: str = ""
    topic: str | None = None
    text: str

    @model_validator(mode="before")
    @classmethod
    def resolve_chat_topic(cls, data: Any) -> Any:
        if isinstance(data, dict):
            val = data.get("chat") or data.get("topic") or ""
            data["chat"] = val
            data["topic"] = val
        return data


class AddWatchlist(BaseModel):
    ticker: str
    note: str | None = None


class RemoveWatchlist(BaseModel):
    ticker: str


class UpsertAnnotation(BaseModel):
    id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    timeframe: str | None = None
    drawing: dict[str, Any]

    @field_validator("drawing")
    @classmethod
    def validate_drawing(cls, value: dict[str, Any]) -> dict[str, Any]:
        import math

        points = value.get("points")
        if not isinstance(value.get("type"), str) or not isinstance(points, list) or not points:
            raise ValueError("drawing requires a type and points")
        for point in points:
            if not isinstance(point, dict):
                raise ValueError("invalid drawing point")
            for key in ("time", "price"):
                number = point.get(key)
                if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
                    raise ValueError("drawing points require finite numeric time and price")
        return value


class StrikeAnnotation(BaseModel):
    id: str


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
