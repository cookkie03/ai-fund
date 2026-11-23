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


class AddDossierNote(BaseModel):
    ticker: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9.\-]+$")
    text: str = Field(min_length=1, max_length=10000)


class DecideProposal(BaseModel):
    proposal_id: int = Field(gt=0)
    action: Literal["accept", "defer", "reject", "ask"]
    reason: str = Field(min_length=1, max_length=10000)
    when: str | None = None
    confirm: bool = False


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


class UpdateRiskLimits(BaseModel):
    limits: dict[str, Any]
    reason: str
    confirm: Literal[True]


class ClosePosition(BaseModel):
    ticker: str
    qty: float | None = None
    order_type: Literal["market", "limit"] = "market"
    limit_price: float | None = None
    dry_run: bool = False
    confirm: bool = False

    @model_validator(mode="after")
    def _check(self) -> ClosePosition:
        if self.qty is not None and self.qty <= 0:
            raise ValueError("qty must be positive")
        if self.order_type == "limit" and (self.limit_price is None or self.limit_price <= 0):
            raise ValueError("limit_price is required for limit orders")
        if not self.dry_run and not self.confirm:
            raise ValueError("confirm must be true")
        return self


class ModifyExit(BaseModel):
    ticker: str
    stop_price: float | None = None
    target_price: float | None = None
    dry_run: bool = False
    confirm: bool = False

    @model_validator(mode="after")
    def _check(self) -> ModifyExit:
        if self.stop_price is None and self.target_price is None:
            raise ValueError("stop_price or target_price is required")
        if not self.dry_run and not self.confirm:
            raise ValueError("confirm must be true")
        return self


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


# --- Bridge & Briefing Commands ---


class BridgeSay(BaseModel):
    conversation_id: int | None = None
    text: str = Field(min_length=1)
    context: dict[str, Any] | None = None


class BridgeRenameConversation(BaseModel):
    conversation_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)


class BridgeArchiveConversation(BaseModel):
    conversation_id: int = Field(gt=0)
    archived: bool = True


class BridgeStop(BaseModel):
    conversation_id: int = Field(gt=0)


class BridgeActionDecide(BaseModel):
    action_id: int = Field(gt=0)
    decision: Literal["confirm", "dismiss"]
    confirm: bool = False

    @model_validator(mode="after")
    def _validate_confirm(self) -> BridgeActionDecide:
        if self.decision == "confirm" and not self.confirm:
            raise ValueError("bridge_action_decide requires confirm: true for decision: 'confirm'")
        return self


class MarkBriefingSeen(BaseModel):
    ts: str | None = None

