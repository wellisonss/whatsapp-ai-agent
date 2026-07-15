"""Cliente HTTP fino para o WAHA (envio, typing, configurar webhook)."""
from __future__ import annotations

import asyncio

import httpx

from ...core.config import get_settings
from ...core.logging import get_logger

log = get_logger(__name__)


class WahaClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        session: str | None = None,
    ) -> None:
        s = get_settings()
        self.base_url = (base_url or s.waha_base_url).rstrip("/")
        self.api_key = api_key or s.waha_api_key
        self.session = session or s.waha_session
        self._headers = {"X-Api-Key": self.api_key, "Content-Type": "application/json"}

    async def configure_webhook(self, public_url: str, retries: int = 3) -> bool:
        url = f"{self.base_url}/api/sessions/{self.session}"
        body = {
            "name": self.session,
            "config": {
                "webhooks": [{
                    "url": public_url,
                    "events": ["message", "message.any", "message.reaction"],
                }]
            },
        }
        backoff = 1.0
        async with httpx.AsyncClient(timeout=10.0) as c:
            for attempt in range(1, retries + 1):
                try:
                    r = await c.put(url, json=body, headers=self._headers)
                    if r.status_code == 200:
                        log.info("waha.webhook.configured", url=public_url)
                        return True
                    log.warning("waha.webhook.failed", status=r.status_code, body=r.text[:200])
                except httpx.HTTPError as e:
                    log.warning("waha.webhook.exception", err=str(e), attempt=attempt)
                if attempt < retries:
                    await asyncio.sleep(backoff)
                    backoff *= 2
        return False

    async def send_text(self, chat_id: str, text: str) -> bool:
        url = f"{self.base_url}/api/sendText"
        body = {"chatId": chat_id, "text": text, "session": self.session}
        async with httpx.AsyncClient(timeout=10.0) as c:
            try:
                r = await c.post(url, json=body, headers=self._headers)
                ok = r.status_code in (200, 201)
                if not ok:
                    log.warning("waha.send.failed", status=r.status_code, body=r.text[:200])
                return ok
            except httpx.HTTPError as e:
                log.error("waha.send.exception", err=str(e))
                return False

    async def send_chunked(self, chat_id: str, text: str, max_len: int = 1600) -> bool:
        if not text:
            return True
        safe = str(text).replace("​", "").replace("\r", "")
        parts: list[str] = []
        while len(safe) > max_len:
            idx = safe.rfind("\n", 0, max_len)
            idx = max_len if idx == -1 else idx
            parts.append(safe[:idx])
            safe = safe[idx:]
        if safe:
            parts.append(safe)
        ok = True
        for i, p in enumerate(parts, 1):
            head = f"(Parte {i}/{len(parts)})\n" if len(parts) > 1 else ""
            ok = await self.send_text(chat_id, head + p) and ok
        return ok

    async def _set_presence(self, chat_id: str, presence: str) -> None:
        url = f"{self.base_url}/api/{self.session}/presence"
        body = {"chatId": chat_id, "presence": presence}
        async with httpx.AsyncClient(timeout=5.0) as c:
            try:
                await c.post(url, json=body, headers=self._headers)
            except httpx.HTTPError as e:
                log.debug("waha.presence.failed", err=str(e), presence=presence)

    async def start_typing(self, chat_id: str) -> None:
        await self._set_presence(chat_id, "typing")

    async def stop_typing(self, chat_id: str) -> None:
        await self._set_presence(chat_id, "paused")
