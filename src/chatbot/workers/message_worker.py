"""Worker assíncrono: consome o stream Redis, debounce, roda o agente, responde via WAHA."""
from __future__ import annotations

import asyncio
import os
import socket

from ..agent.runner import run_agent
from ..core.config import get_settings
from ..core.logging import get_logger, setup_logging
from ..infra.db import init_db
from ..infra.queue import consume
from ..integrations.waha.client import WahaClient

setup_logging()
log = get_logger(__name__)


async def _handle(message: dict) -> None:
    chat_id = message.get("chat_id") or ""
    text = (message.get("text") or "").strip()
    if not chat_id or not text:
        log.info("worker.skip.empty", chat_id=chat_id)
        return

    log.info("worker.process.start", chat_id=chat_id, len=len(text))
    waha = WahaClient()
    try:
        await waha.start_typing(chat_id)
        answer = await run_agent(chat_id, text)
        await waha.send_chunked(chat_id, answer)
        log.info("worker.process.done", chat_id=chat_id)
    except Exception as e:
        err_str = str(e)
        log.error("worker.process.error", chat_id=chat_id, err=err_str[:300])
        if "429" in err_str or "ResourceExhausted" in err_str or "quota" in err_str.lower():
            msg = "Estou sobrecarregado no momento. Aguarde alguns segundos e tente novamente."
        else:
            msg = "Ocorreu um erro interno ao processar sua mensagem. Tente novamente em instantes."
        try:
            await waha.send_text(chat_id, msg)
        except Exception:
            pass
    finally:
        await waha.stop_typing(chat_id)


async def main() -> None:
    setup_logging()
    log.info("worker.boot")
    await init_db()
    consumer = f"{socket.gethostname()}-{os.getpid()}"
    s = get_settings()
    await consume(_handle, consumer_name=consumer)
    # mantém referência ao stream lido
    _ = s


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
