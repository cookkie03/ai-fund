"""Secure secrets manager storing API keys outside repository and DB with 0600 permissions."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

DEFAULT_SECRETS_PATH = Path.home() / ".config" / "trading-agent" / "secrets.env"
DEFAULT_META_PATH = Path.home() / ".config" / "trading-agent" / "secrets.meta.json"

KNOWN_SECRETS = {
    "OMNIROUTE_API_KEY": {"label": "OmniRoute API Key", "capital": False},
    "ALPACA_API_KEY": {"label": "Alpaca API Key", "capital": True},
    "ALPACA_SECRET_KEY": {"label": "Alpaca Secret Key", "capital": True},
    "OPENBB_API_KEY": {"label": "OpenBB API Key", "capital": False},
}


class SecretsManager:
    def __init__(
        self,
        secrets_path: Path | str | None = None,
        meta_path: Path | str | None = None,
    ) -> None:
        env_path = os.environ.get("TRADING_AGENT_SECRETS_PATH")
        self.secrets_path = Path(secrets_path or env_path or DEFAULT_SECRETS_PATH)
        self.meta_path = Path(meta_path or (self.secrets_path.with_name("secrets.meta.json")))
        self._ensure_paths()

    def _ensure_paths(self) -> None:
        try:
            self.secrets_path.parent.mkdir(parents=True, exist_ok=True)
            if not self.secrets_path.exists():
                self.secrets_path.write_text("", encoding="utf-8")
            os.chmod(self.secrets_path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
        except Exception:
            pass

    def load_env_file(self) -> dict[str, str]:
        data: dict[str, str] = {}
        if self.secrets_path.is_file():
            try:
                for line in self.secrets_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        data[k.strip()] = v.strip().strip("'\"")
            except Exception:
                pass
        return data

    def load_meta(self) -> dict[str, Any]:
        if self.meta_path.is_file():
            try:
                return json.loads(self.meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def save_meta(self, meta: dict[str, Any]) -> None:
        try:
            self.meta_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.meta_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
            tmp.replace(self.meta_path)
        except Exception:
            pass

    def get(self, name: str) -> str | None:
        # 1. secrets.env
        vals = self.load_env_file()
        if name in vals and vals[name]:
            return vals[name]
        # 2. os.environ / .env
        return os.environ.get(name)

    def set(self, name: str, value: str, actor: str, reason: str) -> dict[str, Any]:
        if name not in KNOWN_SECRETS:
            raise ValueError(f"Unknown secret name: {name}")
        if not value or not value.strip():
            raise ValueError("Secret value cannot be empty")

        vals = self.load_env_file()
        vals[name] = value.strip()

        # Atomic write to secrets.env with 0600
        lines = [f"{k}={v}" for k, v in vals.items()]
        content = "\n".join(lines) + "\n"

        self.secrets_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.secrets_path.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        tmp.replace(self.secrets_path)

        # Update metadata
        meta = self.load_meta()
        last4 = value.strip()[-4:] if len(value.strip()) >= 4 else "****"
        from storage.office_db import utc_now_iso
        ts = utc_now_iso()
        meta[name] = {
            "last4": last4,
            "updated_ts": ts,
            "updated_by": actor,
            "reason": reason,
            "source": "store",
            "test": None,
        }
        self.save_meta(meta)
        return {"name": name, "set": True, "last4": last4}

    def clear(self, name: str, actor: str, reason: str) -> None:
        if name not in KNOWN_SECRETS:
            raise ValueError(f"Unknown secret name: {name}")
        vals = self.load_env_file()
        if name in vals:
            del vals[name]
            lines = [f"{k}={v}" for k, v in vals.items()]
            content = "\n".join(lines) + ("\n" if lines else "")
            tmp = self.secrets_path.with_suffix(".tmp")
            tmp.write_text(content, encoding="utf-8")
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
            tmp.replace(self.secrets_path)

        meta = self.load_meta()
        if name in meta:
            del meta[name]
            self.save_meta(meta)

    def list_secrets(self) -> list[dict[str, Any]]:
        vals = self.load_env_file()
        meta = self.load_meta()
        out = []
        for name, info in KNOWN_SECRETS.items():
            val = vals.get(name)
            source = "store" if val else ("env" if os.environ.get(name) else "none")
            effective_val = val or os.environ.get(name)
            last4 = meta.get(name, {}).get("last4")
            if not last4 and effective_val and len(effective_val) >= 4:
                last4 = effective_val[-4:]
            m_info = meta.get(name, {})
            out.append({
                "name": name,
                "label": info["label"],
                "set": bool(effective_val),
                "last4": last4 if effective_val else None,
                "updated_ts": m_info.get("updated_ts"),
                "updated_by": m_info.get("updated_by"),
                "source": source if effective_val else "none",
                "test": m_info.get("test"),
            })
        return out

    def record_test(self, name: str, ok: bool, detail: str) -> None:
        meta = self.load_meta()
        if name not in meta:
            meta[name] = {}
        from storage.office_db import utc_now_iso
        meta[name]["test"] = {
            "ok": ok,
            "detail": detail,
            "ts": utc_now_iso(),
        }
        self.save_meta(meta)
