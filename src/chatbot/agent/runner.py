"""Wrapper de alto nível para invocar o agente."""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from ..core.config import get_settings
from ..core.logging import get_logger
from ..core.observability import callbacks
from ..memory.extractor import extract_facts
from ..memory.manager import MemoryManager
from .compaction import maybe_compact
from .graph import get_graph

log = get_logger(__name__)
_mm = MemoryManager()


def _token_header(msgs: list) -> str:
    """Soma tokens de todos os AIMessages e retorna cabeçalho de debug."""
    total_in = total_out = 0
    for m in msgs:
        if not isinstance(m, AIMessage):
            continue
        meta = getattr(m, "usage_metadata", None) or {}
        total_in += meta.get("input_tokens", 0)
        total_out += meta.get("output_tokens", 0)
    if not total_in and not total_out:
        return ""
    return f"📊 _tokens: in={total_in:,} out={total_out:,} total={total_in+total_out:,}_\n\n"


async def run_agent(chat_id: str, user_text: str) -> str:
    """Roda uma volta de conversa para `chat_id`.

    - Continua a sessão via checkpointer (`thread_id=chat_id`).
    - Após responder, extrai fatos e atualiza memória de longo prazo (best-effort).
    """
    graph = await get_graph()
    config = {
        "configurable": {"thread_id": chat_id},
        "callbacks": callbacks(),
        "metadata": {"chat_id": chat_id},
    }
    state_in = {
        "chat_id": chat_id,
        "messages": [HumanMessage(content=user_text)],
    }
    out = await graph.ainvoke(state_in, config)

    msgs = out.get("messages", [])
    last = msgs[-1] if msgs else None
    answer = last.content if isinstance(last, AIMessage) else "Desculpe, não consegui processar."

    # Cabeçalho de debug com contagem de tokens (apenas fora de produção)
    if get_settings().app_env != "production":
        header = _token_header(msgs)
        if header:
            answer = header + str(answer)

    # Compactação proativa do histórico em background (não bloqueia resposta)
    maybe_compact(graph, config, msgs)

    # Atualiza memória de longo prazo em background (não bloqueia resposta)
    try:
        facts = await extract_facts(msgs[-6:])
        if facts:
            await _mm.add_facts(chat_id, facts)
    except Exception as e:  # pragma: no cover
        log.warning("memory.update.failed", err=str(e))

    return str(answer)
