"""Integração com Langfuse para tracing das execuções do agente."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from .config import get_settings
from .logging import get_logger

log = get_logger(__name__)


@lru_cache
def get_langfuse_handler() -> Any | None:
    """Retorna um CallbackHandler do Langfuse para LangChain/LangGraph, ou None."""
    settings = get_settings()
    if not settings.langfuse_enabled:
        return None
    try:
        from langfuse.callback import CallbackHandler  # type: ignore

        handler = CallbackHandler(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        log.info("langfuse.enabled", host=settings.langfuse_host)
        return handler
    except Exception as e:  # pragma: no cover
        log.warning("langfuse.disabled", error=str(e))
        return None


def callbacks() -> list[Any]:
    """Lista de callbacks para passar em invoke()/astream()."""
    h = get_langfuse_handler()
    return [h] if h else []
