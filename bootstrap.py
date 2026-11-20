"""Bootstrap module for Agent Office: wiring real components and test fixtures."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from agents.backend import (
    AgentBackend,
    AgentSpec,
    ChatMessage,
    OpenAICompatibleBackend,
    StepResult,
    ToolSpec,
)
from agents.fake_backend import ScriptedBackend
from config.office_settings import (
    OfficeSettings,
    load_office_settings,
)
from data.cache import DataCache
from execution.order_flow import BracketBroker, OrderFlow
from execution.trade_manager import TradeManager
from prompts.loader import load_prompt
from storage.office_db import OfficeDB
from storage.registry import RegistryWriter
from tools.environment import AgentEnvironment, BrokerReader, MarketData
from workflows.office import Office

logger = logging.getLogger(__name__)

class RoutingBackend(AgentBackend):
    """Routes step() calls to an agent-specific backend based on office settings."""

    def __init__(
        self,
        backends: dict[str, AgentBackend],
        default_backend: AgentBackend,
    ) -> None:
        self.backends = backends
        self.default_backend = default_backend

    def step(
        self,
        agent: AgentSpec,
        chat_context: list[ChatMessage],
        tools: Sequence[ToolSpec],
    ) -> StepResult:
        backend = self.backends.get(agent.name, self.default_backend)
        return backend.step(agent, chat_context, tools)


def resolve_db_path(env: Mapping[str, str] | None = None) -> Path:
    """Single unified resolver for the OfficeDB database file path."""
    env_map = os.environ if env is None else env
    path_str = env_map.get("TRADING_AGENT_DB", "data/trading-agent.db")
    if path_str == ":memory:":
        return Path(":memory:")
    return Path(path_str).resolve()


class SafeBrokerReader:
    """Sanitizes broker account and positions so no paper/live details leak to agents."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def get_account(self) -> dict[str, Any]:
        if hasattr(self._inner, "get_account"):
            acc = self._inner.get_account()
            if hasattr(acc, "equity"):
                equity = float(acc.equity)
                cash = float(acc.cash)
                buying_power = float(getattr(acc, "buying_power", cash))
            elif isinstance(acc, dict):
                equity = float(acc.get("equity", 0.0))
                cash = float(acc.get("cash", 0.0))
                buying_power = float(acc.get("buying_power", cash))
            else:
                equity = 100000.0
                cash = 50000.0
                buying_power = cash
        else:
            equity = 100000.0
            cash = 50000.0
            buying_power = cash

        return {
            "equity": equity,
            "cash": cash,
            "buying_power": buying_power,
        }

    def get_positions(self) -> list[dict[str, Any]]:
        if hasattr(self._inner, "get_positions"):
            positions = self._inner.get_positions()
        else:
            positions = []
        res: list[dict[str, Any]] = []
        for p in positions:
            if isinstance(p, dict):
                qty = p.get("qty")
                if qty is None:
                    qty = p.get("quantity", 0)
                res.append(
                    {
                        "symbol": str(p.get("symbol", "")).upper(),
                        "qty": float(qty),
                        "market_value": float(p.get("market_value", 0.0) or 0.0),
                        "cost_basis": float(p.get("cost_basis", 0.0) or 0.0),
                    }
                )
            else:
                qty = getattr(p, "qty", None)
                if qty is None:
                    qty = getattr(p, "quantity", 0)
                res.append(
                    {
                        "symbol": str(getattr(p, "symbol", "")).upper(),
                        "qty": float(qty),
                        "market_value": float(getattr(p, "market_value", 0.0) or 0.0),
                        "cost_basis": float(getattr(p, "cost_basis", 0.0) or 0.0),
                    }
                )
        return res

    def get_orders(self, query: Any = None) -> list[Any]:
        if hasattr(self._inner, "get_orders"):
            return list(self._inner.get_orders(query))
        return []


class CacheMarketDataAdapter:
    """Adapts DataCache into the MarketData protocol expected by AgentEnvironment."""

    def __init__(self, cache: DataCache) -> None:
        self.cache = cache

    def quote(self, symbol: str) -> dict[str, Any]:
        """Latest daily bar as a quote. Raises if no real data exists: never invents a price."""
        bars = self.cache.get("prices_ohlcv", key=symbol.upper(), interval="1d")
        if not bars:
            raise RuntimeError(f"nessun dato di prezzo disponibile per {symbol.upper()}")
        latest = bars[-1]
        return {
            "symbol": symbol.upper(),
            "price": float(latest["c"]),
            "close": float(latest["c"]),
            "high": float(latest["h"]),
            "low": float(latest["l"]),
            "volume": float(latest["v"]),
            "ts": latest.get("ts"),
        }

    def ohlcv(
        self, symbol: str, interval: str = "1d", limit: int = 100
    ) -> list[dict[str, Any]]:
        """Most recent `limit` bars in ascending time order."""
        bars = list(self.cache.get("prices_ohlcv", key=symbol.upper(), interval=interval))
        return bars[-limit:] if limit > 0 else bars

    def news(
        self, symbol: str | None = None, theme: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        key = symbol.upper() if symbol else (theme or "macro")
        try:
            items = self.cache.get("news", key=key)
            return list(items)[:limit]
        except Exception as exc:
            logger.warning("dati non disponibili: %s", exc)
            return []

    def ratings(self, symbol: str) -> list[dict[str, Any]] | dict[str, Any]:
        try:
            return list(self.cache.get("ratings", key=symbol.upper()))
        except Exception as exc:
            logger.warning("dati non disponibili: %s", exc)
            return []

    def insiders(self, symbol: str, limit: int = 20) -> list[dict[str, Any]]:
        try:
            return list(self.cache.get("insider", key=symbol.upper()))[:limit]
        except Exception as exc:
            logger.warning("dati non disponibili: %s", exc)
            return []

    def financials(self, symbol: str) -> dict[str, Any] | list[dict[str, Any]]:
        try:
            res = self.cache.get("fundamentals", key=symbol.upper())
            if len(res) > 0 and isinstance(res[0], dict):
                return res[0]
            return list(res)
        except Exception as exc:
            logger.warning("dati non disponibili: %s", exc)
            return {}

    def earnings_dates(self, symbol: str) -> list[dict[str, Any]] | dict[str, Any]:
        try:
            return list(self.cache.get("earnings", key=symbol.upper()))
        except Exception as exc:
            logger.warning("dati non disponibili: %s", exc)
            return []

    def macro(self, series_id: str) -> list[dict[str, Any]] | dict[str, Any]:
        try:
            return list(self.cache.get("macro_series", key=series_id))
        except Exception as exc:
            logger.warning("dati non disponibili: %s", exc)
            return []

    def econ_calendar(self, limit: int = 20) -> list[dict[str, Any]]:
        try:
            return list(self.cache.get("econ_calendar"))[:limit]
        except Exception as exc:
            logger.warning("dati non disponibili: %s", exc)
            return []

    def sector_perf(self) -> list[dict[str, Any]] | dict[str, Any]:
        try:
            return list(self.cache.get("sector_performance"))
        except Exception:
            return []


class AlpacaBracketAdapter:
    """Adapts Alpaca TradingClient to the BracketBroker protocol without leaking URLs."""

    def __init__(self, trading_client: Any) -> None:
        self._client = trading_client

    def submit_bracket(
        self,
        client_order_id: str,
        symbol: str,
        side: str,
        qty: Decimal,
        limit_price: Decimal,
        take_profit: Decimal,
        stop_loss: Decimal,
    ) -> str:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, StopLossRequest, TakeProfitRequest

        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        req = LimitOrderRequest(
            symbol=symbol,
            qty=str(qty),
            side=order_side,
            time_in_force=TimeInForce.DAY,
            limit_price=str(limit_price),
            order_class="bracket",
            take_profit=TakeProfitRequest(limit_price=float(take_profit)),
            stop_loss=StopLossRequest(stop_price=str(stop_loss)),
            client_order_id=client_order_id,
        )
        res = self._client.submit_order(req)
        return str(res.id)

    def _leg_id(self, parent_id: str, kind: str) -> str:
        """Id of the stop-loss or take-profit leg of a bracket (the parent has neither)."""
        parent = self._client.get_order_by_id(parent_id)
        for leg in getattr(parent, "legs", None) or []:
            order_type = str(getattr(leg, "order_type", getattr(leg, "type", ""))).lower()
            is_stop = "stop" in order_type
            if (kind == "stop") == is_stop:
                return str(leg.id)
        raise RuntimeError(f"gamba {kind} non trovata per l'ordine {parent_id}")

    def modify_stop(self, broker_order_id: str, stop: Decimal) -> None:
        from alpaca.trading.requests import ReplaceOrderRequest

        req = ReplaceOrderRequest(stop_price=float(stop))
        self._client.replace_order_by_id(self._leg_id(broker_order_id, "stop"), req)

    def modify_take_profit(self, broker_order_id: str, take_profit: Decimal) -> None:
        from alpaca.trading.requests import ReplaceOrderRequest

        req = ReplaceOrderRequest(limit_price=float(take_profit))
        self._client.replace_order_by_id(self._leg_id(broker_order_id, "tp"), req)

    def cancel(self, broker_order_id: str) -> None:
        self._client.cancel_order_by_id(broker_order_id)

    def find_by_client_id(self, client_order_id: str) -> Any | None:
        try:
            return self._client.get_order_by_client_id(client_order_id)
        except Exception:
            return None

    def get_order(self, broker_order_id: str) -> Any | None:
        from alpaca.trading.requests import GetOrderByIdRequest

        try:
            return self._client.get_order_by_id(broker_order_id, filter=GetOrderByIdRequest(nested=True))
        except Exception:
            return None

    def get_open_orders(self, symbol: str | None = None) -> list[Any]:
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        req = GetOrdersRequest(
            status=QueryOrderStatus.OPEN,
            symbols=[symbol] if symbol else None,
        )
        try:
            return list(self._client.get_orders(req))
        except Exception:
            return []

    def is_market_open(self) -> bool:
        try:
            clock = self._client.get_clock()
            return bool(clock.is_open)
        except Exception:
            return True


def _lazy_init_data_cache(db: OfficeDB, env: Mapping[str, str] | None = None) -> DataCache:
    """Lazily import real data providers from data.providers to populate DataCache."""
    providers: dict[str, Callable[..., Any]] = {}
    env_map = os.environ if env is None else env
    prices_choice = (env_map.get("DATA_PRICES_PROVIDER") or "yahoo").strip().lower()
    prices_order = ["openbb", "yahoo"] if prices_choice == "openbb" else ["yahoo", "openbb"]
    for name in prices_order:
        try:
            from data.refresh import adapt_market_data_provider

            if name == "openbb":
                from data.providers.openbb import OpenBBProvider

                prov: Any = OpenBBProvider()
            else:
                from data.providers.yahoo_finance import YahooFinanceProvider

                prov = YahooFinanceProvider()
            providers["prices_ohlcv"] = adapt_market_data_provider(prov)
            logger.info("provider prezzi: %s", name)
            break
        except Exception as exc:
            logger.warning("provider prezzi '%s' non disponibile: %s", name, exc)

    try:
        from data.providers.yahoo_fundamentals import YahooFundamentalsProvider
        from data.refresh import adapt_fundamentals_provider

        fund_prov = YahooFundamentalsProvider()
        providers["fundamentals"] = adapt_fundamentals_provider(fund_prov)
    except Exception as exc:
        logger.warning("provider fondamentali non disponibile: %s", exc)

    try:
        from data.providers.alpaca_news import AlpacaNewsProvider
        from data.refresh import adapt_news_provider

        api_key = env_map.get("ALPACA_API_KEY", "")
        secret_key = env_map.get("ALPACA_SECRET_KEY", "")
        if not (api_key and secret_key):
            raise RuntimeError("ALPACA_API_KEY/ALPACA_SECRET_KEY mancanti")
        from alpaca.data.historical.news import NewsClient

        news_prov = AlpacaNewsProvider(NewsClient(api_key=api_key, secret_key=secret_key))
        providers["news"] = adapt_news_provider(news_prov)
    except Exception as exc:
        logger.warning("provider news non disponibile: %s", exc)

    return DataCache(db=db, providers=providers)


def _lazy_init_alpaca_broker(env: Mapping[str, str]) -> tuple[BracketBroker, BrokerReader]:
    """Lazily initialize Alpaca broker and bracket adapter."""
    api_key = env.get("ALPACA_API_KEY", "")
    secret_key = env.get("ALPACA_SECRET_KEY", "")
    trading_url = env.get("ALPACA_TRADING_URL", "https://paper-api.alpaca.markets/v2")

    if not (api_key and secret_key):
        raise RuntimeError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set to run the engine")

    from alpaca.trading.client import TradingClient

    from brokers.alpaca import AlpacaBroker, _sdk_base_url

    client = TradingClient(
        api_key=api_key,
        secret_key=secret_key,
        paper=True,
        url_override=_sdk_base_url(trading_url),
    )
    return AlpacaBracketAdapter(client), SafeBrokerReader(AlpacaBroker(client))


def build_agent_spec(agent_name: str, settings: OfficeSettings) -> AgentSpec:
    """Build a fully-populated AgentSpec for an agent using load_prompt."""
    cfg = settings.get_agent(agent_name)
    try:
        prompt_text, prompt_hash = load_prompt(agent_name)
    except FileNotFoundError:
        prompt_text, prompt_hash = "", ""
    return AgentSpec(
        name=agent_name,
        role=agent_name,
        model=cfg.model,
        endpoint=cfg.endpoint,
        effort=cfg.effort,
        system_prompt=prompt_text,
        prompt_hash=prompt_hash,
    )


def build_office(
    settings: OfficeSettings | None = None,
    env: Mapping[str, str] | None = None,
    event_log: Any = None,
) -> Office:
    """Build production-grade Office instance wiring real components.

    Never exposes paper/live broker credentials or flags to agents.
    """
    env_map = os.environ if env is None else env

    if settings is None:
        toml_path = Path("config/office.toml")
        if toml_path.is_file():
            settings = load_office_settings(toml_path)
        else:
            settings = OfficeSettings()

    # 1. OfficeDB at configured DB path
    resolved_path = resolve_db_path(env_map)
    if resolved_path != Path(":memory:"):
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
    db = OfficeDB(resolved_path)

    # 2. RegistryWriter
    registry = RegistryWriter(db)

    # 3. AgentBackend per agent from office settings
    agent_backends: dict[str, AgentBackend] = {}
    default_backend = OpenAICompatibleBackend(
        api_key=settings.resolve_api_key("portfolio_manager", env_map)
    )

    agent_specs: dict[str, AgentSpec] = {}
    for agent_name in settings.agents:
        api_key = settings.resolve_api_key(agent_name, env_map)
        agent_backends[agent_name] = OpenAICompatibleBackend(api_key=api_key)
        spec = build_agent_spec(agent_name, settings)
        agent_specs[agent_name] = spec
        cfg = settings.get_agent(agent_name)
        db.register_agent(
            name=agent_name,
            role=agent_name,
            config={"model": cfg.model, "endpoint": cfg.endpoint, "effort": cfg.effort},
            prompt_hash=spec.prompt_hash,
        )

    backend = RoutingBackend(agent_backends, default_backend=default_backend)

    # 4. DataCache with real providers lazily imported
    data_cache = _lazy_init_data_cache(db, env_map)
    market_data = CacheMarketDataAdapter(data_cache)

    # 5. Alpaca broker / Bracket broker lazily
    bracket_broker, broker_reader = _lazy_init_alpaca_broker(env_map)

    # 6. OrderFlow & TradeManager
    trade_manager = TradeManager(db=db, broker=bracket_broker, event_log=event_log)
    order_flow = OrderFlow(
        db=db,
        broker=bracket_broker,
        approval_mode=settings.approval_mode,
        event_log=event_log,
        trade_manager=trade_manager,
        broker_reader=broker_reader,
    )

    # 7. AgentEnvironment factory
    def env_factory(cycle_id: int | None = None) -> AgentEnvironment:
        return AgentEnvironment(
            db=db,
            market_data=market_data,
            broker_reader=broker_reader,
            min_trading_days=settings.scheduled_task_min_days,
            max_trading_days=settings.scheduled_task_max_days,
        )

    office = Office(
        db=db,
        backend=backend,
        env_factory=env_factory,
        order_flow=order_flow,
        settings=settings,
        registry=registry,
        event_log=event_log,
    )

    # Attach convenience references for CLI
    office.trade_manager = trade_manager  # type: ignore[attr-defined]
    office.data_cache = data_cache  # type: ignore[attr-defined]
    office.broker_reader = broker_reader  # type: ignore[attr-defined]
    office.bracket_broker = bracket_broker  # type: ignore[attr-defined]
    office.agent_specs = agent_specs  # type: ignore[attr-defined]

    return office


def build_test_office(
    db: OfficeDB | None = None,
    backend: AgentBackend | None = None,
    market_data: MarketData | None = None,
    broker: Any | None = None,
    broker_reader: BrokerReader | None = None,
    settings: OfficeSettings | None = None,
    clock: Callable[[], datetime] | datetime | None = None,
    approval_mode: str = "auto",
    sleep_fn: Callable[[float], None] | None = None,
    event_log: Any = None,
) -> Office:
    """Build test Office wired with fakes for isolated, fast unit testing."""
    from tests.fakes.bracket_broker import FakeBracketBroker

    test_db = db or OfficeDB(":memory:")
    test_broker = broker or FakeBracketBroker()

    if broker_reader is None:
        reader_src = test_broker if hasattr(test_broker, "get_account") else FakeBracketBroker()
        test_reader: BrokerReader = SafeBrokerReader(reader_src)
    else:
        test_reader = broker_reader

    if market_data is None:
        from tests.workflows.test_office import FakeMarketData

        test_market_data: MarketData = FakeMarketData()
    else:
        test_market_data = market_data

    test_backend = backend or ScriptedBackend([])
    test_settings = settings or OfficeSettings(approval_mode=approval_mode)  # type: ignore[arg-type]

    trade_manager = TradeManager(db=test_db, broker=test_broker, event_log=event_log)
    order_flow = OrderFlow(
        db=test_db,
        broker=test_broker,
        approval_mode=test_settings.approval_mode,
        event_log=event_log,
        trade_manager=trade_manager,
        broker_reader=test_reader,
    )

    def env_factory(cycle_id: int | None = None) -> AgentEnvironment:
        return AgentEnvironment(
            db=test_db,
            market_data=test_market_data,
            broker_reader=test_reader,
            clock=clock if callable(clock) else None,
            now=clock if not callable(clock) else None,
            min_trading_days=test_settings.scheduled_task_min_days,
            max_trading_days=test_settings.scheduled_task_max_days,
        )

    kwargs: dict[str, Any] = {
        "db": test_db,
        "backend": test_backend,
        "env_factory": env_factory,
        "order_flow": order_flow,
        "clock": clock,
        "settings": test_settings,
        "event_log": event_log,
    }
    if sleep_fn is not None:
        kwargs["sleep_fn"] = sleep_fn

    office = Office(**kwargs)

    # Attach convenience references
    office.trade_manager = trade_manager  # type: ignore[attr-defined]
    office.data_cache = None  # type: ignore[attr-defined]
    office.broker_reader = test_reader  # type: ignore[attr-defined]
    office.bracket_broker = test_broker  # type: ignore[attr-defined]

    return office
