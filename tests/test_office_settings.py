"""Tests for office settings loading, validation, and configuration checks."""

from __future__ import annotations

import pytest

from config.office_settings import (
    OfficeSettings,
    check_config,
    load_office_settings,
)


def test_load_default_office_toml() -> None:
    settings = load_office_settings("config/office.toml")
    assert isinstance(settings, OfficeSettings)

    # General settings
    assert settings.max_parallel == 3
    assert settings.approval_mode == "auto"
    assert settings.db_size_alert_mb == 500
    assert settings.scheduled_task_min_days == 1
    assert settings.scheduled_task_max_days == 60

    # Schedule
    assert settings.schedule.market_open == "09:30"
    assert settings.schedule.market_close == "16:00"
    assert settings.schedule.timezone == "America/New_York"

    # Budgets
    assert settings.budgets.cycle_budget == 50
    assert settings.budgets.market_analyst_activation_budget == 15

    # Risk Gate limits
    assert settings.limits.max_risk_per_trade_fraction == 0.01
    assert settings.limits.max_position_fraction == 0.10
    assert settings.limits.max_sector_fraction == 0.30
    assert settings.limits.max_open_positions == 30
    assert settings.limits.min_cash_reserve_fraction == 0.05
    assert settings.limits.min_risk_reward_ratio == 1.5
    assert settings.limits.earnings_embargo_days == 2

    # Retention
    assert settings.retention.daily_prices_days == 1825
    assert settings.retention.weekly_prices_days == 3650
    assert settings.retention.hourly_bars_days == 90
    assert settings.retention.full_news_days == 90
    assert settings.retention.llm_logs_days == 180

    # Agent efforts per MVP spec
    assert settings.get_agent("portfolio_manager").effort == "high"
    assert settings.get_agent("market_analyst").effort == "medium"
    assert settings.get_agent("sentiment_analyst").effort == "medium"
    assert settings.get_agent("technical_analyst").effort == "medium"
    assert settings.get_agent("fundamental_analyst").effort == "medium"
    assert settings.get_agent("risk_analyst").effort == "medium"
    assert settings.get_agent("subagent").effort == "low"


def test_agent_alias_lookup() -> None:
    settings = load_office_settings("config/office.toml")

    assert settings.get_agent("pm") == settings.get_agent("portfolio_manager")
    assert settings.get_agent("market") == settings.get_agent("market_analyst")
    assert settings.get_agent("sentiment") == settings.get_agent("sentiment_analyst")
    assert settings.get_agent("technical") == settings.get_agent("technical_analyst")
    assert settings.get_agent("fundamental") == settings.get_agent("fundamental_analyst")
    assert settings.get_agent("risk") == settings.get_agent("risk_analyst")
    assert settings.get_agent("subagent") is not None

    with pytest.raises(KeyError, match="Unknown agent"):
        settings.get_agent("nonexistent_agent")


def test_resolve_api_key_from_env() -> None:
    settings = load_office_settings("config/office.toml")

    fake_env = {"OMNIROUTE_API_KEY": "omni-secret-999"}
    resolved = settings.resolve_api_key("pm", env=fake_env)
    assert resolved == "omni-secret-999"

    missing = settings.resolve_api_key("pm", env={})
    assert missing is None


def test_missing_settings_file_raises_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_office_settings("config/nonexistent_file.toml")


def test_check_config_valid() -> None:
    settings = load_office_settings("config/office.toml")
    valid_env = {"OMNIROUTE_API_KEY": "sk-test-valid"}

    problems = check_config(settings, env=valid_env)
    assert problems == []


def test_check_config_missing_env_key() -> None:
    settings = load_office_settings("config/office.toml")
    empty_env: dict[str, str] = {}

    problems = check_config(settings, env=empty_env)
    assert len(problems) > 0
    assert any("Missing environment variable 'OMNIROUTE_API_KEY'" in p for p in problems)


def test_check_config_out_of_range_limits() -> None:
    settings = load_office_settings("config/office.toml")
    valid_env = {"OMNIROUTE_API_KEY": "sk-test"}

    # Set invalid risk gate limits
    settings.limits.max_risk_per_trade_fraction = 1.5  # > 1.0
    settings.limits.max_position_fraction = -0.1  # <= 0
    settings.limits.max_open_positions = 0  # < 1
    settings.limits.min_risk_reward_ratio = -1.0  # <= 0

    problems = check_config(settings, env=valid_env)
    assert any("limits.max_risk_per_trade_fraction" in p for p in problems)
    assert any("limits.max_position_fraction" in p for p in problems)
    assert any("limits.max_open_positions" in p for p in problems)
    assert any("limits.min_risk_reward_ratio" in p for p in problems)


def test_check_config_out_of_range_budgets_and_scheduler() -> None:
    settings = load_office_settings("config/office.toml")
    valid_env = {"OMNIROUTE_API_KEY": "sk-test"}

    settings.budgets.cycle_budget = 0
    settings.budgets.market_analyst_activation_budget = -5
    settings.max_parallel = 0
    settings.db_size_alert_mb = -10
    settings.scheduled_task_min_days = 10
    settings.scheduled_task_max_days = 5  # max < min

    problems = check_config(settings, env=valid_env)
    assert any("budgets.cycle_budget" in p for p in problems)
    assert any("budgets.market_analyst_activation_budget" in p for p in problems)
    assert any("max_parallel" in p for p in problems)
    assert any("db_size_alert_mb" in p for p in problems)
    assert any("scheduled_task_max_days must be >= scheduled_task_min_days" in p for p in problems)


def test_llm_endpoint_env_override(monkeypatch):
    from config.office_settings import load_office_settings

    monkeypatch.setenv("OFFICE_LLM_ENDPOINT", "http://omniroute:20128/v1")
    settings = load_office_settings("config/office.toml")
    assert settings.agents
    assert all(a.endpoint == "http://omniroute:20128/v1" for a in settings.agents.values())
