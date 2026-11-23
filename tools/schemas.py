"""Pydantic input schemas for Agent Office tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ReadStateInput(BaseModel):
    """Input for reading the current shared state for a ticker."""

    ticker: str = Field(description="Ticker symbol to read state for (e.g. AAPL)")


class ReadPortfolioInput(BaseModel):
    """Input for reading current portfolio account, positions, and orders."""


class SendMessageInput(BaseModel):
    """Input for sending a message to another agent."""

    to_agent: str = Field(description=(
            "Recipient agent name, one of: portfolio_manager, sentiment_analyst, "
            "technical_analyst, fundamental_analyst, risk_analyst, market_analyst"
        ))
    ticker_or_theme: str = Field(
        description="Ticker symbol or macro/sector theme the message pertains to"
    )
    text: str = Field(description="Body of the message")


class CallSubagentInput(BaseModel):
    """Input for delegating a bounded read-only research task to a subagent."""

    task: str = Field(description="Task description for the subagent to execute")


class WriteAnalysisInput(BaseModel):
    """Input for an analyst updating their section of ticker analysis."""

    ticker: str = Field(description="Ticker symbol")
    section_text: str = Field(description="Analysis text from this specialist analyst")


class SuggestInput(BaseModel):
    """Input for an analyst suggesting trading direction and conviction."""

    ticker: str = Field(description="Ticker symbol")
    direction: Literal["buy", "sell", "hold"] = Field(
        description="Suggested trading direction: buy, sell, or hold"
    )
    conviction: float = Field(
        ge=0.0,
        le=1.0,
        description="Conviction level between 0.0 (weakest) and 1.0 (strongest)",
    )


class SetCoefficientsInput(BaseModel):
    """Input for setting order calculation coefficients."""

    ticker: str = Field(description="Ticker symbol")
    k_entry: float | None = Field(
        default=None,
        description="ATR entry offset multiplier (Risk Analyst only, >= 0.0)",
    )
    risk_fraction: float | None = Field(
        default=None,
        description="Fraction of equity risked on trade (Risk Analyst only, in (0, 1])",
    )
    k_stop: float | None = Field(
        default=None,
        description="ATR stop loss multiplier (Technical Analyst only, > 0.0)",
    )
    k_tp: float | None = Field(
        default=None,
        description="ATR take profit multiplier (Technical Analyst only, > 0.0)",
    )
    k_trail_act: float | None = Field(
        default=None,
        description="ATR trailing activation offset (Technical Analyst only, > 0.0)",
    )
    k_trail: float | None = Field(
        default=None,
        description="ATR trailing distance multiplier (Technical Analyst only, > 0.0)",
    )


# --- Data Tools: Market Analyst ---


class MacroInput(BaseModel):
    """Input for fetching a macroeconomic data series."""

    series_id: str = Field(description="Macro series identifier (e.g. CPI, GDP, UNRATE)")


class NewsByThemeInput(BaseModel):
    """Input for fetching news by macro or sector theme."""

    theme: str = Field(description="Topic or theme name (e.g. technology, semiconductors, energy)")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum number of items")


class EconCalendarInput(BaseModel):
    """Input for fetching economic calendar events."""

    limit: int = Field(default=20, ge=1, le=100, description="Maximum number of events")


class SectorPerfInput(BaseModel):
    """Input for fetching sector performance."""


class SetSectorViewInput(BaseModel):
    """Input for Market Analyst to update the market outlook for a sector (US 77)."""

    sector: str = Field(description="Sector name (e.g. Technology, Healthcare)")
    view: str = Field(description="Market and sector outlook analysis text")


class ScheduleTaskInput(BaseModel):
    """Input for scheduling a future task."""

    chat: str = Field(description="Chat topic or ticker for the scheduled task")
    when: str = Field(description="Target UTC datetime in ISO 8601 format")
    reason: str = Field(description="Reason for scheduling this task")


# --- Data Tools: Sentiment Analyst ---


class NewsByTickerInput(BaseModel):
    """Input for fetching news related to a specific ticker."""

    ticker: str = Field(description="Ticker symbol")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum number of news items")


class RatingsInput(BaseModel):
    """Input for fetching analyst ratings for a ticker."""

    ticker: str = Field(description="Ticker symbol")


class InsidersInput(BaseModel):
    """Input for fetching insider trading transactions for a ticker."""

    ticker: str = Field(description="Ticker symbol")
    limit: int = Field(default=20, ge=1, le=100, description="Maximum number of transactions")


# --- Data Tools: Technical Analyst ---


class QuoteInput(BaseModel):
    """Input for fetching the latest price quote for a ticker."""

    ticker: str = Field(description="Ticker symbol")


class OHLCVInput(BaseModel):
    """Input for fetching historical OHLCV price bars."""

    ticker: str = Field(description="Ticker symbol")
    interval: str | None = Field(default=None, description="Bar interval; defaults to configured timeframe")
    limit: int = Field(default=100, ge=1, le=500, description="Number of bars")


class IndicatorsInput(BaseModel):
    """Input for computing technical indicators on the fly."""

    ticker: str = Field(description="Ticker symbol")
    indicators: list[str] | None = Field(
        default=None,
        description=(
            "Specific indicator names (e.g. ['SMA', 'RSI', 'MACD', 'ATR', 'pivot']), or all if None"
        ),
    )


# --- Data Tools: Fundamental Analyst ---


class FinancialsInput(BaseModel):
    """Input for fetching company financials."""

    ticker: str = Field(description="Ticker symbol")


class RatiosInput(BaseModel):
    """Input for fetching financial ratios for a company."""

    ticker: str = Field(description="Ticker symbol")


class EarningsDatesInput(BaseModel):
    """Input for fetching earnings dates and surprises."""

    ticker: str = Field(description="Ticker symbol")


# --- Data Tools: Risk Analyst ---


class PortfolioRiskInput(BaseModel):
    """Input for evaluating portfolio exposures, concentration, and open risk."""


class CurrentDraftInput(BaseModel):
    """Input for inspecting the current order draft for a ticker."""

    ticker: str = Field(description="Ticker symbol")


# --- PM Only Tools ---


class ReadDraftInput(BaseModel):
    """Input for reading the current order draft for a ticker."""

    ticker: str = Field(description="Ticker symbol")


class AcceptOrderInput(BaseModel):
    """Input for Portfolio Manager to accept an order draft."""

    ticker: str = Field(description="Ticker symbol")
    action: Literal["buy", "sell"] = Field(
        description="Order action: buy, or sell on an open position"
    )
    reason: str = Field(description="Detailed rationale for the decision")


class DeferInput(BaseModel):
    """Input for Portfolio Manager to defer decision on a ticker."""

    ticker: str = Field(description="Ticker symbol")
    reason: str = Field(description="Reason for deferring decision")


class WatchlistGetInput(BaseModel):
    """Input for reading the current watchlist."""


class WatchlistSetInput(BaseModel):
    """Input for modifying the watchlist."""

    action: Literal["add", "remove", "set"] = Field(
        default="add",
        description="Action: 'add' ticker, 'remove' ticker, or 'set' whole watchlist",
    )
    ticker: str | None = Field(default=None, description="Single ticker symbol")
    tickers: list[str] | None = Field(default=None, description="List of ticker symbols")
    note: str = Field(default="", description="Optional note for the ticker(s)")


class ScheduleNextCheckInput(BaseModel):
    """Input for scheduling the next check date/time for a ticker."""

    ticker: str = Field(description="Ticker symbol")
    when: str = Field(description="Target UTC datetime in ISO 8601 format")
    note: str = Field(default="", description="Reason or note for next check")
