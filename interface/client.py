"""Client interface for communicating with the Runtime over HTTP."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx
from pydantic import BaseModel

from runtime.commands import CommandResult

logger = logging.getLogger(__name__)


class RuntimeUnavailable(RuntimeError):
    """Raised when the Runtime HTTP server cannot be reached."""


class RuntimeClient:
    """Thin client communicating with the single-writer Runtime process."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8765",
        token: str | None = None,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._custom_client = client
        self._timeout = timeout

    def _get_client(self) -> httpx.Client:
        if self._custom_client is not None:
            return self._custom_client
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=self._timeout,
        )

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        client = self._get_client()
        should_close = client is not self._custom_client
        try:
            return client.request(method, url, **kwargs)
        finally:
            if should_close:
                client.close()

    def command(
        self,
        name: str,
        payload: dict[str, Any] | BaseModel | None = None,
        actor: str = "cli",
        command_id: str | None = None,
    ) -> CommandResult:
        """Send a typed command to the Runtime."""
        cid = command_id or str(uuid.uuid4())
        data = (
            payload.model_dump()
            if isinstance(payload, BaseModel)
            else (payload if payload is not None else {})
        )

        headers = {
            "Idempotency-Key": cid,
            "X-Actor": actor,
        }

        try:
            resp = self._request("POST", f"/v1/commands/{name}", json=data, headers=headers)
            if resp.status_code == 422:
                return CommandResult(ok=False, reasons=[f"Invalid input: {resp.text}"])
            resp.raise_for_status()
            res_dict = resp.json()
            return CommandResult.model_validate(res_dict)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise RuntimeUnavailable(
                f"Runtime non attivo su {self.base_url}: avvialo con 'trading-agent run' (o docker compose up)."
            ) from exc
        except httpx.HTTPStatusError as exc:
            return CommandResult(ok=False, reasons=[f"HTTP {exc.response.status_code}: {exc.response.text}"])
        except Exception as exc:
            raise RuntimeUnavailable(
                f"Runtime non attivo su {self.base_url}: {exc}"
            ) from exc

    def read(self, name: str, params: dict[str, Any] | None = None) -> Any:
        """Query read model from the Runtime."""
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            resp = self._request("GET", f"/v1/read/{name}", params=clean_params)
            resp.raise_for_status()
            return resp.json()
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise RuntimeUnavailable(
                f"Runtime non attivo su {self.base_url}: avvialo con 'trading-agent run' (o docker compose up)."
            ) from exc
        except Exception as exc:
            raise RuntimeUnavailable(
                f"Runtime non attivo su {self.base_url}: {exc}"
            ) from exc

    def health(self) -> dict[str, Any]:
        """Check Runtime health."""
        try:
            resp = self._request("GET", "/v1/health")
            resp.raise_for_status()
            return resp.json()
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise RuntimeUnavailable(
                f"Runtime non attivo su {self.base_url}: avvialo con 'trading-agent run' (o docker compose up)."
            ) from exc
        except Exception as exc:
            raise RuntimeUnavailable(
                f"Runtime non attivo su {self.base_url}: {exc}"
            ) from exc
