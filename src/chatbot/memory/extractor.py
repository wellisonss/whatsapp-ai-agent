"""Extrai automaticamente fatos da conversa via LLM (formato JSON estrito)."""
from __future__ import annotations

import json
import re
from typing import Iterable

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from ..agent.llm import get_llm
from ..core.logging import get_logger

log = get_logger(__name__)

_EXTRACT_PROMPT = (
    "Você é um extrator de memória de longo prazo de um assistente virtual.\n"
    "A partir do trecho de conversa abaixo, extraia até 5 FATOS estáveis sobre o "
    "usuário (preferências, papel, tópicos que costuma consultar, métricas favoritas, "
    "estilo de resposta etc.) que valham guardar entre sessões.\n"
    "Ignore fatos efêmeros (pedidos pontuais, datas específicas, valores).\n"
    "Responda APENAS um JSON: {\"facts\": [\"...\", \"...\"]}.\n"
    "Se não houver nada relevante, responda {\"facts\": []}.\n"
)


def _conversation_text(messages: Iterable[BaseMessage]) -> str:
    parts = []
    for m in messages:
        role = m.type.upper()
        content = (getattr(m, "content", "") or "").strip()
        if content:
            parts.append(f"{role}: {content}")
    return "\n".join(parts[-12:])


async def extract_facts(messages: Iterable[BaseMessage]) -> list[str]:
    convo = _conversation_text(messages)
    if not convo:
        return []
    llm = get_llm(temperature=0.0)
    resp = await llm.ainvoke([
        SystemMessage(content=_EXTRACT_PROMPT),
        HumanMessage(content=convo),
    ])
    text = (resp.content or "").strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
        facts = data.get("facts", [])
        return [str(f).strip() for f in facts if f and isinstance(f, str)][:5]
    except Exception as e:
        log.warning("memory.extract.parse_error", err=str(e), raw=text[:200])
        return []
