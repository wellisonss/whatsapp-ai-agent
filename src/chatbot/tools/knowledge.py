"""Tool de RAG: consulta a base de conhecimento institucional da empresa."""
from __future__ import annotations

from langchain_core.tools import tool

from ..rag.retriever import format_docs, retrieve


@tool
def retrieve_knowledge(query: str, top_n: int = 4) -> str:
    """Recupera trechos da base de conhecimento institucional (história, missão,
    valores, unidades, políticas etc.) usando hybrid search + rerank.

    Use SOMENTE para perguntas institucionais/educacionais sobre a empresa.
    NÃO use para faturamento/vendas (use buscar_faturamento_itens)."""
    docs = retrieve(query, k=8, top_n=top_n)
    return format_docs(docs) or "Nenhum trecho relevante encontrado na base."
