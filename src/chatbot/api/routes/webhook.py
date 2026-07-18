"""Webhook do WAHA — apenas valida e enfileira; processamento fica no worker."""
from __future__ import annotations

from fastapi import APIRouter, Request

from ...core.config import get_settings
from ...core.logging import get_logger
from ...infra.queue import enqueue
from ...integrations.waha.client import WahaClient
from ...integrations.waha.models import WahaWebhook

router = APIRouter()
log = get_logger(__name__)


def _extract_phone(chat_id: str) -> str:
    """Remove sufixo @c.us / @g.us, retorna só o número."""
    return chat_id.split("@")[0]


@router.post("/webhook/waha")
async def waha_webhook(request: Request) -> dict:
    raw = await request.json()
    if raw.get("event") != "message":
        return {"status": "ignored", "event": raw.get("event")}

    try:
        payload = WahaWebhook.model_validate(raw)
    except Exception as e:
        log.warning("webhook.invalid_payload", err=str(e))
        return {"status": "error", "reason": "invalid_payload"}

    msg = payload.payload
    if msg.fromMe:
        return {"status": "ignored", "reason": "fromMe"}

    text = (msg.body or "").strip()
    chat_id = msg.from_ or msg.participant or ""

    if not text or not chat_id:
        return {"status": "ignored", "reason": "empty"}

    # Em grupos, from_ é o ID do grupo e participant é quem enviou.
    # Em DMs, from_ é o remetente e participant é vazio.
    sender_id = msg.participant or msg.from_ or ""

    # NOWEB envia @lid em vez de @c.us; o número real fica em _data.key.remoteJidAlt
    if "@lid" in sender_id:
        try:
            alt = (msg.model_extra or {}).get("_data", {}).get("key", {}).get("remoteJidAlt", "")
            if alt:
                sender_id = alt
        except Exception:
            pass

    phone = _extract_phone(sender_id)
    log.info("webhook.received", phone=phone, chat_id=chat_id)

    allowed = get_settings().allowed_numbers
    if allowed and phone not in allowed:
        log.info("webhook.ignored", phone=phone, reason="number_not_allowed")
        is_group = "@g.us" in chat_id
        if not is_group:
            await WahaClient().send_text(
                chat_id,
                "Desculpe, você não tem permissão para usar este assistente.",
            )
        return {"status": "ignored", "reason": "number_not_allowed"}

    await enqueue({
        "chat_id": chat_id,
        "text": text,
        "message_id": msg.id,
        "session": payload.session,
        "timestamp": msg.timestamp,
    })
    log.info("webhook.queued", phone=phone)
    return {"status": "queued"}
