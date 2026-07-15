"""Fila de webhooks: Redis Streams + dedup por message_id + debounce por chat_id.

API:
    enqueue(message)                          → coloca na fila (com dedup)
    consume(handler, group, consumer_name)    → loop de consumo no worker
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Awaitable, Callable

from ..core.config import get_settings
from ..core.logging import get_logger
from .redis_client import get_redis

log = get_logger(__name__)

DEDUP_TTL_SECONDS = 60 * 60  # 1h


def _dedup_key(message_id: str) -> str:
    return f"chatbot:dedup:{message_id}"


def _debounce_key(chat_id: str) -> str:
    return f"chatbot:debounce:{chat_id}"


def _buffer_key(chat_id: str) -> str:
    return f"chatbot:buffer:{chat_id}"


async def enqueue(message: dict) -> bool:
    """Enfileira mensagem inbound. Retorna False se duplicada (já vista)."""
    s = get_settings()
    r = get_redis()

    msg_id = message.get("message_id") or message.get("id") or ""
    if msg_id:
        # SET NX = só seta se não existir (dedup atômico)
        was_new = await r.set(_dedup_key(msg_id), "1", nx=True, ex=DEDUP_TTL_SECONDS)
        if not was_new:
            log.info("queue.dedup", message_id=msg_id)
            return False

    chat_id = message.get("chat_id") or ""
    text = message.get("text") or ""

    # Buffer textual + janela de debounce: mensagens em sequência viram uma só
    if chat_id and text:
        await r.rpush(_buffer_key(chat_id), text)
        # marca instante da última mensagem desse chat
        await r.set(_debounce_key(chat_id), str(time.time()), ex=300)

    await r.xadd(s.inbox_stream, {"data": json.dumps(message, ensure_ascii=False)})
    log.info("queue.enqueued", chat_id=chat_id, message_id=msg_id, stream=s.inbox_stream)
    return True


async def _drain_buffer(chat_id: str) -> str:
    r = get_redis()
    parts: list[str] = []
    while True:
        item = await r.lpop(_buffer_key(chat_id))
        if item is None:
            break
        parts.append(item)
    return "\n".join(parts).strip()


async def _wait_debounce(chat_id: str, debounce: float) -> None:
    """Espera até que `debounce` segundos sem novas mensagens passem."""
    r = get_redis()
    while True:
        ts = await r.get(_debounce_key(chat_id))
        if not ts:
            return
        elapsed = time.time() - float(ts)
        if elapsed >= debounce:
            return
        await asyncio.sleep(debounce - elapsed + 0.05)


async def consume(
    handler: Callable[[dict], Awaitable[None]],
    consumer_name: str,
    block_ms: int = 5000,
) -> None:
    """Loop infinito de consumo do stream com consumer group."""
    s = get_settings()
    r = get_redis()
    stream = s.inbox_stream
    group = s.inbox_group

    try:
        await r.xgroup_create(stream, group, id="0", mkstream=True)
    except Exception:  # já existe
        pass

    log.info("queue.consume.start", stream=stream, group=group, consumer=consumer_name)

    while True:
        try:
            entries = await r.xreadgroup(
                groupname=group, consumername=consumer_name,
                streams={stream: ">"}, count=8, block=block_ms,
            )
        except Exception as e:  # pragma: no cover
            log.error("queue.read.error", err=str(e))
            await asyncio.sleep(1.0)
            continue

        if not entries:
            continue

        for _stream, msgs in entries:
            for msg_id, fields in msgs:
                try:
                    payload = json.loads(fields.get("data") or "{}")
                except Exception as e:
                    log.error("queue.decode.error", err=str(e))
                    await r.xack(stream, group, msg_id)
                    continue

                chat_id = payload.get("chat_id") or ""

                # Debounce: se houver outras mensagens chegando, espera estabilizar
                try:
                    if chat_id:
                        await _wait_debounce(chat_id, s.inbox_debounce_seconds)
                        merged_text = await _drain_buffer(chat_id)
                        if merged_text:
                            payload["text"] = merged_text

                    await handler(payload)
                except Exception as e:
                    log.exception("queue.handler.error", err=str(e), chat_id=chat_id)
                finally:
                    await r.xack(stream, group, msg_id)
