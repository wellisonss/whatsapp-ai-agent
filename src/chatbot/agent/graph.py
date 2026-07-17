"""Construção do grafo LangGraph do agente.

Topologia:
    [START] → load_memory → agent ⇄ tools → format → [END]

- load_memory: carrega fatos de longo prazo (Postgres) e injeta no system prompt.
- agent: chama o LLM com tools bound; pode pedir tool call.
- tools: ToolNode executa as tools quando o LLM pediu.
- format: pós-processamento leve da resposta para WhatsApp.

Persistência da sessão (curto prazo) via PostgresSaver.
"""
from __future__ import annotations

from functools import lru_cache

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from ..core.config import get_settings
from ..core.logging import get_logger
from ..memory.manager import MemoryManager
from ..tools import ALL_TOOLS
from .llm import get_llm
from .prompts import build_system_prompt
from .state import AgentState

# Máximo de mensagens recentes enviadas ao LLM por turno.
# Mensagens mais antigas são compactadas em resumo XML (ver compaction.py).
_MAX_HISTORY_MESSAGES = 8

log = get_logger(__name__)

_memory_manager = MemoryManager()


def _strip_unsafe_glyphs(text: str) -> str:
    return (text.replace("→", "->").replace("←", "<-")
                .replace("↑", "^").replace("↓", "v"))


async def _node_load_memory(state: AgentState) -> AgentState:
    chat_id = state.get("chat_id") or ""
    facts_block = await _memory_manager.render_for_prompt(chat_id) if chat_id else ""
    return {"user_facts_block": facts_block}


def _build_agent_node():
    llm_with_tools = get_llm().bind_tools(ALL_TOOLS)

    async def _node_agent(state: AgentState) -> AgentState:
        system = SystemMessage(content=build_system_prompt(state.get("user_facts_block", "")))
        history = state.get("messages", [])

        # Se existe um resumo compactado das mensagens antigas, injeta como contexto.
        summary = state.get("history_summary", "")
        if summary:
            summary_msg = SystemMessage(content=f"<previous-context>\n{summary}\n</previous-context>")
            extra = [summary_msg]
        else:
            extra = []

        # Limita mensagens recentes enviadas ao LLM para controlar tokens.
        if len(history) > _MAX_HISTORY_MESSAGES:
            recent = history[-_MAX_HISTORY_MESSAGES:]
            # Gemini exige que a sequência comece num HumanMessage.
            for i, m in enumerate(recent):
                if isinstance(m, HumanMessage):
                    recent = recent[i:]
                    break
            else:
                recent = history[-1:]  # fallback: só a última mensagem
            log.debug("agent.history.trimmed", total=len(history), kept=len(recent))
            history = recent

        msgs = [system, *extra, *history]
        resp = await llm_with_tools.ainvoke(msgs)
        return {"messages": [resp]}

    return _node_agent


def _route_after_agent(state: AgentState) -> str:
    last = state.get("messages", [])[-1] if state.get("messages") else None
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tools"
    return "format"


async def _node_format(state: AgentState) -> AgentState:
    last = state.get("messages", [])[-1] if state.get("messages") else None
    if not isinstance(last, AIMessage):
        return {}
    cleaned = _strip_unsafe_glyphs(str(last.content or ""))
    if cleaned == last.content:
        return {}
    return {"messages": [AIMessage(content=cleaned, id=last.id)]}


@lru_cache
def _build_uncompiled_graph() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("load_memory", _node_load_memory)
    g.add_node("agent", _build_agent_node())
    g.add_node("tools", ToolNode(ALL_TOOLS))
    g.add_node("format", _node_format)

    g.add_edge(START, "load_memory")
    g.add_edge("load_memory", "agent")
    g.add_conditional_edges("agent", _route_after_agent, {"tools": "tools", "format": "format"})
    g.add_edge("tools", "agent")
    g.add_edge("format", END)
    return g


_compiled = None
_checkpointer_ctx = None


async def get_graph():
    """Compila o grafo (uma vez) com o checkpointer Postgres."""
    global _compiled, _checkpointer_ctx
    if _compiled is not None:
        return _compiled

    s = get_settings()
    _checkpointer_ctx = AsyncPostgresSaver.from_conn_string(s.postgres_dsn)
    saver = await _checkpointer_ctx.__aenter__()
    await saver.setup()

    _compiled = _build_uncompiled_graph().compile(checkpointer=saver)
    log.info("agent.graph.compiled")
    return _compiled
