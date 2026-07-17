"""Estado do grafo do agente (LangGraph)."""
from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """Estado mantido por sessão (chat_id).

    `messages` recebe `add_messages` para append automático.
    `chat_id` identifica o usuário (para memória de longo prazo).
    `user_facts_block` é o bloco de fatos injetado no system prompt.
    `history_summary` é o resumo compactado das mensagens antigas (gerado por compaction).
    """
    messages: Annotated[list[BaseMessage], add_messages]
    chat_id: str
    user_facts_block: str
    history_summary: str
