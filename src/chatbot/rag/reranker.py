"""Reranking opcional dos top-K via Cohere (ou pass-through quando OFF)."""
from __future__ import annotations

from typing import Sequence

from langchain_core.documents import Document

from ..core.config import get_settings
from ..core.logging import get_logger

log = get_logger(__name__)


def rerank(query: str, docs: Sequence[Document], top_n: int) -> list[Document]:
    s = get_settings()
    if s.reranker == "off" or not docs:
        return list(docs)[:top_n]
    if s.reranker == "cohere":
        try:
            import cohere  # type: ignore

            co = cohere.Client(api_key=s.cohere_api_key)
            res = co.rerank(
                query=query,
                documents=[d.page_content for d in docs],
                model="rerank-multilingual-v3.0",
                top_n=top_n,
            )
            order = [r.index for r in res.results]
            return [docs[i] for i in order]
        except Exception as e:  # pragma: no cover
            log.warning("rerank.cohere.failed", err=str(e))
            return list(docs)[:top_n]
    return list(docs)[:top_n]
