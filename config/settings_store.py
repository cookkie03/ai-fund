"""Versioned office settings store backed by OfficeDB, overriding office.toml defaults."""

from __future__ import annotations

import json
from typing import Any

from config.office_settings import OfficeSettings, load_office_settings

SETTINGS_SCHEMA: dict[str, dict[str, Any]] = {
    "max_parallel": {"type": "int", "min": 1, "max": 32, "apply": "live", "section": "mercato", "label": "Concorrenza massima", "description": "Numero massimo di cicli di analisi eseguiti in parallelo."},
    "approval_mode": {"type": "enum", "options": ["auto", "manual"], "apply": "restart", "section": "mercato", "label": "Modalità approvazione", "description": "Invio automatico al broker o richiesta di approvazione manuale.", "capital": True},
    "db_size_alert_mb": {"type": "int", "min": 10, "max": 10000, "apply": "live", "section": "dati", "label": "Soglia avviso DB (MB)", "description": "Allarme quando il database SQLite supera questa dimensione."},
    "scheduled_task_min_days": {"type": "int", "min": 1, "max": 365, "apply": "live", "section": "mercato", "label": "Min giorni task schedulati", "description": "Limiti in giorni di borsa per Scheduled tasks."},
    "scheduled_task_max_days": {"type": "int", "min": 1, "max": 365, "apply": "live", "section": "mercato", "label": "Max giorni task schedulati", "description": "Limiti in giorni di borsa per Scheduled tasks."},
    "market.bar_timeframe": {"type": "enum", "options": ["1m", "5m", "15m", "1h", "1d"], "apply": "restart", "section": "mercato", "label": "Timeframe predefinito", "description": "Timeframe predefinito del grafico. Nota: cambiare timeframe richiede attenzione sui coefficienti k."},
    "schedule.market_open": {"type": "time", "apply": "restart", "section": "mercato", "label": "Apertura mercato", "description": "Orario di apertura sessione US (HH:MM)."},
    "schedule.market_close": {"type": "time", "apply": "restart", "section": "mercato", "label": "Chiusura mercato", "description": "Orario di chiusura sessione US (HH:MM)."},
    "schedule.premarket_open": {"type": "time", "apply": "restart", "section": "mercato", "label": "Apertura pre-market", "description": "Orario di apertura pre-market (HH:MM)."},
    "schedule.timezone": {"type": "string", "apply": "restart", "section": "mercato", "label": "Timezone", "description": "Fuso orario di riferimento (es. America/New_York)."},
    "budgets.cycle_budget": {"type": "int", "min": 1, "max": 1000, "apply": "live", "section": "agenti", "label": "Budget ciclo", "description": "Budget messaggi e chiamate subagent per ciclo."},
    "budgets.market_analyst_activation_budget": {"type": "int", "min": 1, "max": 1000, "apply": "live", "section": "agenti", "label": "Budget Market Analyst", "description": "Budget per singola attivazione del Market Analyst."},
    "retention.daily_prices_days": {"type": "int", "min": 1, "max": 7300, "apply": "live", "section": "dati", "label": "Retention barre giornaliere", "description": "Giorni di conservazione barre giornaliere."},
    "retention.weekly_prices_days": {"type": "int", "min": 1, "max": 7300, "apply": "live", "section": "dati", "label": "Retention barre settimanali", "description": "Giorni di conservazione barre settimanali."},
    "retention.hourly_bars_days": {"type": "int", "min": 1, "max": 365, "apply": "live", "section": "dati", "label": "Retention barre orarie", "description": "Giorni di conservazione barre orarie."},
    "retention.full_news_days": {"type": "int", "min": 1, "max": 365, "apply": "live", "section": "dati", "label": "Retention news complete", "description": "Giorni di conservazione testo completo news."},
    "retention.llm_logs_days": {"type": "int", "min": 1, "max": 365, "apply": "live", "section": "dati", "label": "Retention log LLM", "description": "Giorni di conservazione prompt e risposte LLM."},
}


class SettingsValidationError(ValueError):
    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def get_nested(obj: Any, path: str) -> Any:
    parts = path.split(".")
    curr = obj
    for p in parts:
        if isinstance(curr, dict):
            curr = curr.get(p)
        else:
            curr = getattr(curr, p, None)
    return curr


def set_nested(d: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    curr = d
    for p in parts[:-1]:
        if p not in curr or not isinstance(curr[p], dict):
            curr[p] = {}
        curr = curr[p]
    curr[parts[-1]] = value


class SettingsStore:
    def __init__(self, db: Any, default_settings: OfficeSettings | None = None) -> None:
        self.db = db
        self.base_settings = default_settings or load_office_settings()

    def latest_version_row(self) -> dict[str, Any] | None:
        if hasattr(self.db, "latest_settings_version"):
            return self.db.latest_settings_version()
        return None

    def active_dict(self) -> dict[str, Any]:
        # Build dictionary of default settings
        base = self.base_settings.model_dump()
        row = self.latest_version_row()
        if row and row.get("after_json"):
            try:
                overrides = json.loads(row["after_json"])
                for k, v in overrides.items():
                    set_nested(base, k, v)
            except Exception:
                pass
        return base

    def active_settings(self) -> OfficeSettings:
        d = self.active_dict()
        return OfficeSettings.model_validate(d)

    def validate_partial(self, partial: dict[str, Any]) -> dict[str, Any]:
        reasons: list[str] = []
        clean: dict[str, Any] = {}
        if not partial:
            raise SettingsValidationError(["Nessuna impostazione da modificare"])
        for k, raw in partial.items():
            if k not in SETTINGS_SCHEMA and not k.startswith("agents."):
                reasons.append(f"Impostazione sconosciuta: {k}")
                continue
            if k.startswith("agents."):
                # agents.<id>.model, endpoint, effort, daily_budget_usd
                parts = k.split(".")
                if len(parts) != 3 or parts[2] not in ("model", "endpoint", "effort", "daily_budget_usd"):
                    reasons.append(f"Impostazione agente non valida: {k}")
                    continue
                clean[k] = raw
                continue

            meta = SETTINGS_SCHEMA[k]
            t = meta["type"]
            if t == "int":
                try:
                    val = int(raw)
                except (TypeError, ValueError):
                    reasons.append(f"{k}: deve essere un intero ({raw!r})")
                    continue
                if "min" in meta and val < meta["min"]:
                    reasons.append(f"{k}: {val} minore del minimo ({meta['min']})")
                    continue
                if "max" in meta and val > meta["max"]:
                    reasons.append(f"{k}: {val} maggiore del massimo ({meta['max']})")
                    continue
                clean[k] = val
            elif t == "enum":
                if raw not in meta["options"]:
                    reasons.append(f"{k}: valore non valido {raw!r}, ammessi {meta['options']}")
                    continue
                clean[k] = raw
            elif t == "time" or t == "string":
                if not isinstance(raw, str) or not raw.strip():
                    reasons.append(f"{k}: stringa non valida")
                    continue
                clean[k] = raw.strip()
            else:
                clean[k] = raw

        if reasons:
            raise SettingsValidationError(reasons)
        return clean

    def preview(self, partial: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        clean = self.validate_partial(partial)
        current = self.active_dict()
        changes = []
        warnings = []
        for k, new_val in clean.items():
            old_val = get_nested(current, k)
            if old_val != new_val:
                meta = SETTINGS_SCHEMA.get(k, {"apply": "live", "label": k})
                apply_mode = meta.get("apply", "live")
                changes.append({
                    "key": k,
                    "old": old_val,
                    "new": new_val,
                    "apply": apply_mode,
                    "ok": True,
                    "reason": None,
                })
                if k == "market.bar_timeframe":
                    warnings.append("Attenzione: cambiare il timeframe richiede attenzione sui coefficienti k.")
        return changes, warnings

    def update(self, partial: dict[str, Any], reason: str, actor: str) -> dict[str, Any]:
        clean = self.validate_partial(partial)
        if not reason or not reason.strip():
            raise SettingsValidationError(["Il motivo è obbligatorio"])
        current_dict = self.active_dict()
        row = self.latest_version_row()

        before_subset: dict[str, Any] = {}
        after_overrides: dict[str, Any] = json.loads(row["after_json"]) if (row and row.get("after_json")) else {}

        changed = {}
        for k, v in clean.items():
            old_v = get_nested(current_dict, k)
            if old_v != v:
                before_subset[k] = old_v
                after_overrides[k] = v
                changed[k] = v

        if not changed:
            raise SettingsValidationError(["Nessuna differenza rispetto alle impostazioni attive"])

        new_version = self.db.insert_settings_version(
            actor=actor,
            reason=reason.strip(),
            before=before_subset,
            after=after_overrides,
        )

        # Event log
        if hasattr(self.db, "event_log") and self.db.event_log is not None:
            self.db.event_log.append(
                type="settings.updated",
                subject=f"settings:{new_version}",
                payload={
                    "version": new_version,
                    "updated_by": actor,
                    "reason": reason.strip(),
                    "keys": list(changed.keys()),
                },
                actor=actor,
            )

        return {
            "version": new_version,
            "updated_ts": row.get("ts") if row else None,
            "keys": list(changed.keys()),
        }

    def restore(self, version: int, reason: str, actor: str) -> dict[str, Any]:
        if not reason or not reason.strip():
            raise SettingsValidationError(["Il motivo è obbligatorio"])
        versions = self.db.list_settings_versions(limit=200)
        target = next((v for v in versions if int(v["version"]) == version), None)
        if not target:
            raise SettingsValidationError([f"Versione impostazioni {version} non trovata"])
        after_json = target["after_json"]
        overrides = json.loads(after_json)
        # Apply as a new version restoring those overrides
        current_dict = self.active_dict()
        before_subset = {k: get_nested(current_dict, k) for k in overrides}
        new_version = self.db.insert_settings_version(
            actor=actor,
            reason=f"Ripristino v{version}: {reason.strip()}",
            before=before_subset,
            after=overrides,
        )
        if hasattr(self.db, "event_log") and self.db.event_log is not None:
            self.db.event_log.append(
                type="settings.updated",
                subject=f"settings:{new_version}",
                payload={
                    "version": new_version,
                    "updated_by": actor,
                    "reason": reason.strip(),
                    "keys": list(overrides.keys()),
                },
                actor=actor,
            )
        return {"version": new_version}

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.list_settings_versions(limit=limit)
        out = []
        for r in rows:
            before = json.loads(r["before_json"])
            after = json.loads(r["after_json"])
            changes = [{"key": k, "old": before.get(k), "new": after.get(k)} for k in before.keys() | after.keys()]
            out.append({
                "version": int(r["version"]),
                "ts": r["ts"],
                "actor": r["actor"],
                "reason": r["reason"],
                "changes": changes,
            })
        return out
