"""Limiti del Risk Gate versionati nel DB.

`office.toml` resta il default iniziale (versione 0, virtuale). Ogni modifica dal cockpit crea una
nuova versione in `risk_limits_versions` con attore, motivo, prima e dopo. Il Risk Gate legge la
versione attiva a ogni valutazione tramite `active_gate_limits`, mai una copia presa all'avvio.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from execution.risk_gate import RiskGateLimits

if TYPE_CHECKING:
    from storage.office_db import OfficeDB

# nome API -> (attributo di RiskGateLimits, tipo)
LIMIT_FIELDS: dict[str, tuple[str, type]] = {
    "max_risk_per_trade_fraction": ("max_risk_per_trade", float),
    "max_position_fraction": ("max_position_size", float),
    "max_sector_fraction": ("max_sector_exposure", float),
    "max_open_positions": ("max_open_positions", int),
    "min_cash_reserve_fraction": ("min_cash_reserve", float),
    "min_risk_reward_ratio": ("min_risk_reward", float),
    "earnings_embargo_days": ("earnings_blackout_trading_days", int),
}

# Limiti prudenti ammessi per le modifiche dal cockpit (min, max inclusi).
BOUNDS: dict[str, tuple[float, float]] = {
    "max_risk_per_trade_fraction": (0.001, 0.05),
    "max_position_fraction": (0.01, 0.25),
    "max_sector_fraction": (0.05, 0.60),
    "max_open_positions": (1, 100),
    "min_cash_reserve_fraction": (0.0, 0.50),
    "min_risk_reward_ratio": (1.0, 10.0),
    "earnings_embargo_days": (0, 10),
}


class LimitsValidationError(ValueError):
    """Valori fuori dai bounds o campi sconosciuti; `reasons` elenca ogni violazione."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


@dataclass(frozen=True)
class ActiveLimits:
    version: int
    updated_ts: str | None
    updated_by: str | None
    limits: dict[str, float | int]


def defaults_from_settings(settings_limits: Any) -> dict[str, float | int]:
    return {name: typ(getattr(settings_limits, name)) for name, (_, typ) in LIMIT_FIELDS.items()}


def bounds_payload() -> dict[str, dict[str, float]]:
    return {name: {"min": lo, "max": hi} for name, (lo, hi) in BOUNDS.items()}


def validate_partial(partial: dict[str, Any]) -> dict[str, float | int]:
    """Valida e normalizza un aggiornamento parziale; solleva LimitsValidationError."""
    reasons: list[str] = []
    clean: dict[str, float | int] = {}
    if not partial:
        raise LimitsValidationError(["Nessun limite da modificare"])
    for name, raw in partial.items():
        if name not in LIMIT_FIELDS:
            reasons.append(f"Limite sconosciuto: {name}")
            continue
        typ = LIMIT_FIELDS[name][1]
        lo, hi = BOUNDS[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            reasons.append(f"{name}: valore non numerico ({raw!r})")
            continue
        if typ is int and float(raw) != int(raw):
            reasons.append(f"{name}: deve essere un intero ({raw!r})")
            continue
        value = typ(raw)
        if value < lo or value > hi:
            reasons.append(f"{name}: {value} fuori dai bounds [{lo}, {hi}]")
            continue
        clean[name] = value
    if reasons:
        raise LimitsValidationError(reasons)
    return clean


class RiskLimitsStore:
    """Accesso ai limiti attivi e alla cronologia delle versioni."""

    def __init__(self, db: OfficeDB, defaults: dict[str, float | int]) -> None:
        self.db = db
        self.defaults = dict(defaults)

    def active(self) -> ActiveLimits:
        row = self.db.latest_risk_limits_version()
        if row is None:
            return ActiveLimits(0, None, None, dict(self.defaults))
        limits = {**self.defaults, **json.loads(row["after_json"])}
        return ActiveLimits(int(row["version"]), row["ts"], row["actor"], limits)

    def gate_limits(self) -> RiskGateLimits:
        return gate_limits_from(self.active().limits)

    def update(self, partial: dict[str, Any], reason: str, actor: str) -> ActiveLimits:
        """Crea una nuova versione, una voce di Inbox e l'evento `risk_limits.updated`.

        Va chiamato dentro `db.transaction()`: l'evento arriva sul bus solo al commit.
        """
        clean = validate_partial(partial)
        if not reason or not reason.strip():
            raise LimitsValidationError(["Il motivo è obbligatorio"])
        before = self.active()
        after = {**before.limits, **clean}
        changed = {k: v for k, v in clean.items() if before.limits.get(k) != v}
        if not changed:
            raise LimitsValidationError(["Nessuna differenza rispetto ai limiti attivi"])
        version = self.db.insert_risk_limits_version(
            actor=actor,
            reason=reason.strip(),
            before={k: before.limits[k] for k in changed},
            after=after,
        )
        summary = ", ".join(f"{k} {before.limits[k]} → {v}" for k, v in changed.items())
        self.db.add_inbox(
            "risk_limits_updated", f"Limiti di rischio v{version} ({actor}): {summary}. {reason}"
        )
        active = self.active()
        if self.db.event_log is not None:
            self.db.event_log.append(
                type="risk_limits.updated",
                subject=f"risk_limits:{version}",
                payload={
                    "version": version,
                    "updated_by": actor,
                    "reason": reason.strip(),
                    "before": {k: before.limits[k] for k in changed},
                    "after": {k: v for k, v in changed.items()},
                    "limits": active.limits,
                },
                actor=actor,
            )
        return active

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        out = []
        for row in self.db.list_risk_limits_versions(limit):
            out.append(
                {
                    "version": int(row["version"]),
                    "ts": row["ts"],
                    "actor": row["actor"],
                    "reason": row["reason"],
                    "before": json.loads(row["before_json"]),
                    "after": {
                        k: v
                        for k, v in json.loads(row["after_json"]).items()
                        if k in json.loads(row["before_json"])
                    },
                }
            )
        return out


def gate_limits_from(limits: dict[str, float | int]) -> RiskGateLimits:
    kwargs: dict[str, Any] = {}
    for name, (attr, typ) in LIMIT_FIELDS.items():
        v = limits[name]
        kwargs[attr] = int(v) if typ is int else Decimal(str(v))
    return RiskGateLimits(**kwargs)


def active_gate_limits(db: OfficeDB, settings_limits: Any) -> RiskGateLimits:
    """Limiti da passare al Risk Gate: versione attiva nel DB, altrimenti default di office.toml."""
    return RiskLimitsStore(db, defaults_from_settings(settings_limits)).gate_limits()
