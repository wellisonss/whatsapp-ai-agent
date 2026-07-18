"""Endpoints administrativos: reconfigurar webhook, indexar KB."""
from __future__ import annotations

from fastapi import APIRouter

from ...core.config import get_settings
from ...integrations.waha.client import WahaClient

router = APIRouter(prefix="/admin")


@router.post("/configure-webhook")
async def configure_webhook() -> dict:
    s = get_settings()
    ok = await WahaClient().configure_webhook(s.webhook_public_url)
    return {"ok": ok, "url": s.webhook_public_url}
