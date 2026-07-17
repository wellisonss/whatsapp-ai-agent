"""Compactação proativa do histórico de sessão.

Quando o histórico de mensagens cresce além de COMPACTION_THRESHOLD, as mensagens
mais antigas são resumidas em XML compacto e removidas do checkpoint LangGraph.
Isso evita explosão de tokens sem perder contexto relevante.

O processo ocorre em background (não bloqueia a resposta ao usuário).
"""
from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from ..core.logging import get_logger
from .llm import get_llm

log = get_logger(__name__)

# Inicia compactação quando histórico tiver mais que este número de mensagens.
COMPACTION_THRESHOLD = 20
# Quantas mensagens recentes manter intactas após compactar.
MESSAGES_TO_KEEP = 6

_COMPACTION_PROMPT = """<task>
Você receberá um histórico de conversa entre um usuário e um assistente virtual.
Crie um resumo compacto em XML preservando todo contexto necessário para continuar a conversa.
</task>

<analysis-instructions>
- Identifique: perguntas feitas, dados consultados, resultados relevantes, preferências do usuário.
- Descarte: saudações, mensagens de erro transitórias, tool calls sem resultado útil.
- Preserve: entidades mencionadas, períodos consultados, tópicos de interesse, decisões tomadas.
</analysis-instructions>

<summary-format>
Retorne SOMENTE o XML abaixo, sem texto adicional:

<session-summary>
  <context>Resumo do que o usuário está buscando e o fluxo da conversa até agora.</context>
  <data-consulted>Dados já consultados via tools (parâmetros e valores-chave).</data-consulted>
  <user-preferences>Preferências ou padrões de consulta observados.</user-preferences>
  <last-state>O que foi discutido mais recentemente antes das mensagens recentes.</last-state>
</session-summary>
</summary-format>

<compression-rules>
- Seja conciso: máximo 300 palavras no total.
- Números e períodos importantes devem ser preservados.
- Omita detalhes de itens individuais a menos que sejam o foco principal.
</compression-rules>

Histórico a compactar:
{history_text}"""


def _format_messages_for_summary(messages: list) -> str:
    parts = []
    for m in messages:
        if isinstance(m, HumanMessage):
            parts.append(f"[Usuário]: {m.content}")
        elif isinstance(m, AIMessage):
            content = m.content or ""
            if getattr(m, "tool_calls", None):
                calls = ", ".join(tc["name"] for tc in m.tool_calls)
                parts.append(f"[Assistente chamou tools]: {calls}")
            elif content:
                parts.append(f"[Assistente]: {content[:400]}")
        elif isinstance(m, ToolMessage):
            content = str(m.content or "")
            parts.append(f"[Tool resultado]: {content[:200]}")
        elif isinstance(m, SystemMessage):
            pass  # system messages já estão no prompt principal
    return "\n".join(parts)


async def compact_session(graph, config: dict, all_messages: list) -> None:
    """Compacta histórico antigo em background.

    Remove as mensagens antigas do checkpoint LangGraph e substitui pelo resumo XML.
    As últimas MESSAGES_TO_KEEP mensagens são preservadas intactas.
    """
    if len(all_messages) <= COMPACTION_THRESHOLD:
        return

    old_msgs = all_messages[:-MESSAGES_TO_KEEP]
    recent_msgs = all_messages[-MESSAGES_TO_KEEP:]

    # Garante que as mensagens a remover não quebrem sequências de tool calls
    # nas mensagens recentes (busca o primeiro HumanMessage nos recentes)
    cutoff = 0
    for i, m in enumerate(recent_msgs):
        if isinstance(m, HumanMessage):
            cutoff = i
            break
    if cutoff > 0:
        old_msgs = old_msgs + recent_msgs[:cutoff]
        recent_msgs = recent_msgs[cutoff:]

    history_text = _format_messages_for_summary(old_msgs)
    if not history_text.strip():
        return

    try:
        llm = get_llm()
        prompt = _COMPACTION_PROMPT.format(history_text=history_text)
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        summary_xml = str(resp.content or "").strip()

        if not summary_xml:
            return

        # Remove mensagens antigas do checkpoint via RemoveMessage
        from langgraph.graph.message import RemoveMessage  # noqa: PLC0415

        removes = [RemoveMessage(id=m.id) for m in old_msgs if getattr(m, "id", None)]

        await graph.aupdate_state(
            config,
            {"messages": removes, "history_summary": summary_xml},
        )

        log.info(
            "compaction.done",
            removed=len(old_msgs),
            kept=len(recent_msgs),
            summary_len=len(summary_xml),
        )

    except Exception as e:
        log.warning("compaction.failed", err=str(e)[:200])


def maybe_compact(graph, config: dict, all_messages: list) -> None:
    """Dispara compactação em background se necessário (non-blocking)."""
    if len(all_messages) > COMPACTION_THRESHOLD:
        asyncio.create_task(compact_session(graph, config, all_messages))
