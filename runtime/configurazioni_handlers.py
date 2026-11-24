"""Command handlers for settings, prompts, secrets, and backups."""

from __future__ import annotations

import logging
from typing import Any

from config.settings_store import SettingsStore, SettingsValidationError
from prompts.loader import compute_prompt_diff, normalize_agent_name
from runtime.commands import (
    BackupDB,
    ClearSecret,
    CommandResult,
    RestorePrompt,
    RestoreSettings,
    SetSecret,
    TestConnection,
    UpdatePrompt,
    UpdateSettings,
)
from storage.backup import create_db_backup
from storage.secrets import SecretsManager

logger = logging.getLogger(__name__)


def handle_update_settings(ctx: Any, cmd: UpdateSettings, actor: str) -> CommandResult:
    store = SettingsStore(ctx.office.db, ctx.office.settings)
    if cmd.dry_run:
        try:
            changes, warnings = store.preview(cmd.changes)
            return CommandResult(ok=True, data={"changes": changes, "warnings": warnings})
        except SettingsValidationError as exc:
            return CommandResult(ok=False, reasons=exc.reasons)

    if "approval_mode" in cmd.changes and not cmd.confirm:
        return CommandResult(ok=False, reasons=["approval_mode richiede confirm: true (azione su capitale)"])

    try:
        with ctx.office.db.transaction():
            res = store.update(cmd.changes, cmd.reason, actor)
            ctx.office.settings = store.active_settings()
        return CommandResult(ok=True, data=res)
    except SettingsValidationError as exc:
        return CommandResult(ok=False, reasons=exc.reasons)


def handle_restore_settings(ctx: Any, cmd: RestoreSettings, actor: str) -> CommandResult:
    store = SettingsStore(ctx.office.db, ctx.office.settings)
    try:
        with ctx.office.db.transaction():
            res = store.restore(cmd.version, cmd.reason, actor)
            ctx.office.settings = store.active_settings()
        return CommandResult(ok=True, data=res)
    except SettingsValidationError as exc:
        return CommandResult(ok=False, reasons=exc.reasons)


def handle_update_prompt(ctx: Any, cmd: UpdatePrompt, actor: str) -> CommandResult:
    canonical = normalize_agent_name(cmd.agent)
    from prompts.loader import load_prompt
    try:
        old_text, _, _, _ = load_prompt(canonical, db=None)
    except Exception:
        old_text = ""

    if cmd.dry_run:
        diff = compute_prompt_diff(old_text, cmd.text)
        return CommandResult(ok=True, data={"agent": canonical, "diff": diff, "chars": len(cmd.text)})

    if not cmd.reason or not cmd.reason.strip():
        return CommandResult(ok=False, reasons=["Il motivo è obbligatorio"])

    with ctx.office.db.transaction():
        version, chars = ctx.office.db.insert_prompt_version(
            agent=canonical,
            actor=actor,
            reason=cmd.reason.strip(),
            text=cmd.text,
        )
        if hasattr(ctx, "event_log") and ctx.event_log is not None:
            ctx.event_log.append(
                type="prompt.updated",
                subject=f"prompt:{canonical}:{version}",
                payload={"agent": canonical, "version": version, "updated_by": actor, "reason": cmd.reason.strip()},
                actor=actor,
            )
    return CommandResult(ok=True, data={"agent": canonical, "version": version, "chars": chars})


def handle_restore_prompt(ctx: Any, cmd: RestorePrompt, actor: str) -> CommandResult:
    canonical = normalize_agent_name(cmd.agent)
    if not cmd.reason or not cmd.reason.strip():
        return CommandResult(ok=False, reasons=["Il motivo è obbligatorio"])
    versions = ctx.office.db.list_prompt_versions(canonical, limit=200)
    target = next((v for v in versions if int(v["version"]) == cmd.version), None)
    if not target:
        return CommandResult(ok=False, reasons=[f"Versione prompt {cmd.version} non trovata per {canonical}"])

    with ctx.office.db.transaction():
        version, chars = ctx.office.db.insert_prompt_version(
            agent=canonical,
            actor=actor,
            reason=f"Ripristino v{cmd.version}: {cmd.reason.strip()}",
            text=target["text"],
        )
        if hasattr(ctx, "event_log") and ctx.event_log is not None:
            ctx.event_log.append(
                type="prompt.updated",
                subject=f"prompt:{canonical}:{version}",
                payload={"agent": canonical, "version": version, "updated_by": actor, "reason": cmd.reason.strip()},
                actor=actor,
            )
    return CommandResult(ok=True, data={"agent": canonical, "version": version, "chars": chars})


def handle_set_secret(ctx: Any, cmd: SetSecret, actor: str) -> CommandResult:
    manager = SecretsManager()
    if cmd.name in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY") and not cmd.confirm:
        return CommandResult(ok=False, reasons=["Le chiavi del broker richiedono confirm: true"])

    try:
        res = manager.set(cmd.name, cmd.value, actor, cmd.reason)
        with ctx.office.db.transaction():
            if hasattr(ctx, "event_log") and ctx.event_log is not None:
                ctx.event_log.append(
                    type="secret.updated",
                    subject=f"secret:{cmd.name}",
                    payload={"name": cmd.name, "set": True, "updated_by": actor},
                    actor=actor,
                )
        return CommandResult(ok=True, data=res)
    except Exception as exc:
        return CommandResult(ok=False, reasons=[str(exc)])


def handle_clear_secret(ctx: Any, cmd: ClearSecret, actor: str) -> CommandResult:
    if not cmd.confirm:
        return CommandResult(ok=False, reasons=["clear_secret richiede confirm: true"])
    manager = SecretsManager()
    try:
        manager.clear(cmd.name, actor, cmd.reason)
        with ctx.office.db.transaction():
            if hasattr(ctx, "event_log") and ctx.event_log is not None:
                ctx.event_log.append(
                    type="secret.updated",
                    subject=f"secret:{cmd.name}",
                    payload={"name": cmd.name, "set": False, "updated_by": actor},
                    actor=actor,
                )
        return CommandResult(ok=True, data={"name": cmd.name, "set": False})
    except Exception as exc:
        return CommandResult(ok=False, reasons=[str(exc)])


def handle_test_connection(ctx: Any, cmd: TestConnection, actor: str) -> CommandResult:
    manager = SecretsManager()
    target = cmd.target.lower()
    ok = True
    detail = "Connessione riuscita (mock/simulata)"

    if target == "omniroute":
        key = manager.get("OMNIROUTE_API_KEY")
        if not key:
            ok = False
            detail = "OMNIROUTE_API_KEY non impostata"
    elif target == "alpaca":
        k1 = manager.get("ALPACA_API_KEY")
        k2 = manager.get("ALPACA_SECRET_KEY")
        if not k1 or not k2:
            ok = False
            detail = "Coppia chiavi Alpaca incompleta"

    for name in manager.KNOWN_SECRETS:
        if target in name.lower() or (target == "alpaca" and "ALPACA" in name):
            manager.record_test(name, ok, detail)

    return CommandResult(ok=True, data={"target": target, "ok": ok, "detail": detail})


def handle_backup_db(ctx: Any, cmd: BackupDB, actor: str) -> CommandResult:
    try:
        res = create_db_backup(ctx.office.db)
        with ctx.office.db.transaction():
            if hasattr(ctx, "event_log") and ctx.event_log is not None:
                ctx.event_log.append(
                    type="health.changed",
                    subject="backup",
                    payload={"name": res["name"], "size_bytes": res["size_bytes"]},
                    actor=actor,
                )
        return CommandResult(ok=True, data=res)
    except Exception as exc:
        return CommandResult(ok=False, reasons=[str(exc)])
