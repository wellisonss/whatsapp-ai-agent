"""Pipeline de recuperação: hybrid search no Qdrant + rerank opcional."""
from __future__ import annotations

from langchain_core.documents import Document

from ..core.logging import get_logger
from ..infra.vectorstore import build_vector_store
from .embeddings import get_embeddings
from .reranker import rerank

log = get_logger(__name__)


def retrieve(query: str, k: int = 8, top_n: int = 4) -> list[Document]:
    """Busca k candidatos via hybrid search e devolve top_n após rerank."""
    if not query.strip():
        return []
    vs = build_vector_store(get_embeddings())
    candidates = vs.similarity_search(query, k=k)
    log.info("rag.retrieve", query_len=len(query), k=k, found=len(candidates))
    return rerank(query, candidates, top_n=top_n)


def format_docs(docs: list[Document]) -> str:
    """Formata em bloco textual para o prompt do agente."""
    if not docs:
        return ""
    blocks = []
    for i, d in enumerate(docs, 1):
        path = d.metadata.get("heading_path") or d.metadata.get("source") or ""
        blocks.append(f"[{i}] ({path})\n{d.page_content.strip()}")
    return "\n\n".join(blocks)
