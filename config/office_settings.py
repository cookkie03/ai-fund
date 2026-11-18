"""Office settings loaded from TOML configuration file."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

EffortLevel = Literal["low", "medium", "high"]
ApprovalMode = Literal["auto", "manual"]


class AgentConfig(BaseModel):
    """Configuration for a single agent runtime."""

    endpoint: str = "http://100.74.207.0:20128/v1"
    model: str = "my-combo"
    effort: EffortLevel = "medium"
    api_key_env: str | None = "OMNIROUTE_API_KEY"
    system_prompt_path: str | None = None


def default_agents() -> dict[str, AgentConfig]:
    """Default agent configuration per MVP spec:

    - Portfolio Manager: effort high
    - Specialists (Market, Sentiment, Technical, Fundamental, Risk): effort medium
    - Subagent: effort low
    """
    return {
        "portfolio_manager": AgentConfig(effort="high", api_key_env="OMNIROUTE_API_KEY"),
        "market_analyst": AgentConfig(effort="medium", api_key_env="OMNIROUTE_API_KEY"),
        "sentiment_analyst": AgentConfig(effort="medium", api_key_env="OMNIROUTE_API_KEY"),
        "technical_analyst": AgentConfig(effort="medium", api_key_env="OMNIROUTE_API_KEY"),
        "fundamental_analyst": AgentConfig(effort="medium", api_key_env="OMNIROUTE_API_KEY"),
        "risk_analyst": AgentConfig(effort="medium", api_key_env="OMNIROUTE_API_KEY"),
        "subagent": AgentConfig(effort="low", api_key_env="OMNIROUTE_API_KEY"),
    }


class RiskGateLimits(BaseModel):
    """Risk Gate hard limits from MVP spec."""

    max_risk_per_trade_fraction: float = 0.01  # <= 1% equity
    max_position_fraction: float = 0.10  # <= 10% equity
    max_sector_fraction: float = 0.30  # <= 30% equity
    max_open_positions: int = 30  # <= 30 positions
    min_cash_reserve_fraction: float = 0.05  # >= 5% cash reserve
    min_risk_reward_ratio: float = 1.5  # R:R >= 1.5
    earnings_embargo_days: int = 2  # no new entry within 2 trading days of earnings


class ScheduleHours(BaseModel):
    """Trading schedule and market session hours."""

    market_open: str = "09:30"
    market_close: str = "16:00"
    premarket_open: str = "09:00"
    timezone: str = "America/New_York"


class BudgetsConfig(BaseModel):
    """Cycle and activation budgets to prevent infinite loops."""

    cycle_budget: int = 50  # generous message and subagent budget per cycle
    market_analyst_activation_budget: int = 15  # budget per standalone Market Analyst run


class RetentionConfig(BaseModel):
    """Data and log retention policies (days)."""

    daily_prices_days: int = 1825  # 5 years, then downsample to weekly
    weekly_prices_days: int = 3650  # 10 years, then downsample to monthly
    hourly_bars_days: int = 90  # 90 days, then downsample to daily
    full_news_days: int = 90  # 90 days, then keep headline and summary
    llm_logs_days: int = 180  # 180 days, then keep metadata only


_AGENT_ALIASES: dict[str, str] = {
    "pm": "portfolio_manager",
    "portfolio_manager": "portfolio_manager",
    "market": "market_analyst",
    "market_analyst": "market_analyst",
    "sentiment": "sentiment_analyst",
    "sentiment_analyst": "sentiment_analyst",
    "technical": "technical_analyst",
    "technical_analyst": "technical_analyst",
    "fundamental": "fundamental_analyst",
    "fundamental_analyst": "fundamental_analyst",
    "risk": "risk_analyst",
    "risk_analyst": "risk_analyst",
    "subagent": "subagent",
}


class OfficeSettings(BaseModel):
    """Complete office configuration loaded from config/office.toml."""

    agents: dict[str, AgentConfig] = Field(default_factory=default_agents)
    limits: RiskGateLimits = Field(default_factory=RiskGateLimits)
    schedule: ScheduleHours = Field(default_factory=ScheduleHours)
    budgets: BudgetsConfig = Field(default_factory=BudgetsConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    max_parallel: int = 3
    db_size_alert_mb: int = 500
    approval_mode: ApprovalMode = "auto"
    scheduled_task_min_days: int = 1
    scheduled_task_max_days: int = 60

    def get_agent(self, name: str) -> AgentConfig:
        """Retrieve agent config by standard name or common alias."""
        key = name.lower().strip().replace(" ", "_").replace("-", "_")
        canonical = _AGENT_ALIASES.get(key, key)
        if canonical in self.agents:
            return self.agents[canonical]
        raise KeyError(f"Unknown agent: '{name}'")

    def resolve_api_key(
        self, agent_name: str, env: Mapping[str, str] | None = None
    ) -> str | None:
        """Resolve the secret API key for an agent from the environment."""
        cfg = self.get_agent(agent_name)
        if not cfg.api_key_env:
            return None
        env_map = os.environ if env is None else env
        return env_map.get(cfg.api_key_env)


def load_office_settings(path: str | Path = "config/office.toml") -> OfficeSettings:
    """Load and validate office settings from a TOML file."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Office settings file not found: {p}")
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    return OfficeSettings.model_validate(data)


def check_config(
    settings: OfficeSettings,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """Check configuration and environment for missing keys or invalid values.

    Returns a list of human-readable problem descriptions for the 'config check' CLI command.
    """
    problems: list[str] = []
    env_map = os.environ if env is None else env

    # 1. Check agent configurations and secrets in env
    for agent_name, agent_cfg in settings.agents.items():
        if agent_cfg.api_key_env:
            val = env_map.get(agent_cfg.api_key_env)
            if not val or not val.strip():
                problems.append(
                    f"Missing environment variable '{agent_cfg.api_key_env}' "
                    f"for agent '{agent_name}'"
                )
        if not agent_cfg.endpoint or not (
            agent_cfg.endpoint.startswith("http://") or agent_cfg.endpoint.startswith("https://")
        ):
            problems.append(f"Invalid endpoint URL '{agent_cfg.endpoint}' for agent '{agent_name}'")
        if not agent_cfg.model or not agent_cfg.model.strip():
            problems.append(f"Model cannot be empty for agent '{agent_name}'")
        if agent_cfg.effort not in ("low", "medium", "high"):
            problems.append(f"Invalid effort level '{agent_cfg.effort}' for agent '{agent_name}'")

    # 2. Check limits (Risk Gate)
    lim = settings.limits
    if not (0.0 < lim.max_risk_per_trade_fraction <= 1.0):
        problems.append("limits.max_risk_per_trade_fraction must be in (0, 1]")
    if not (0.0 < lim.max_position_fraction <= 1.0):
        problems.append("limits.max_position_fraction must be in (0, 1]")
    if not (0.0 < lim.max_sector_fraction <= 1.0):
        problems.append("limits.max_sector_fraction must be in (0, 1]")
    if lim.max_open_positions < 1:
        problems.append("limits.max_open_positions must be >= 1")
    if not (0.0 <= lim.min_cash_reserve_fraction < 1.0):
        problems.append("limits.min_cash_reserve_fraction must be in [0, 1)")
    if lim.min_risk_reward_ratio <= 0.0:
        problems.append("limits.min_risk_reward_ratio must be > 0")
    if lim.earnings_embargo_days < 0:
        problems.append("limits.earnings_embargo_days must be >= 0")

    # 3. Check budgets
    if settings.budgets.cycle_budget < 1:
        problems.append("budgets.cycle_budget must be >= 1")
    if settings.budgets.market_analyst_activation_budget < 1:
        problems.append("budgets.market_analyst_activation_budget must be >= 1")

    # 4. Concurrency, DB alerts, scheduled task day limits
    if settings.max_parallel < 1:
        problems.append("max_parallel must be >= 1")
    if settings.db_size_alert_mb <= 0:
        problems.append("db_size_alert_mb must be > 0")
    if settings.scheduled_task_min_days < 1:
        problems.append("scheduled_task_min_days must be >= 1")
    if settings.scheduled_task_max_days < settings.scheduled_task_min_days:
        problems.append("scheduled_task_max_days must be >= scheduled_task_min_days")

    # 5. Retention
    ret = settings.retention
    if (
        ret.daily_prices_days < 1
        or ret.weekly_prices_days < 1
        or ret.hourly_bars_days < 1
        or ret.full_news_days < 1
        or ret.llm_logs_days < 1
    ):
        problems.append("retention days must be >= 1")

    return problems
