"""Embeddings via Gemini (langchain-google-genai)."""
from __future__ import annotations

from functools import lru_cache

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from ..core.config import get_settings


@lru_cache
def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    s = get_settings()
    return GoogleGenerativeAIEmbeddings(
        model=f"models/{s.embedding_model}",
        google_api_key=s.google_api_key,
    )


def embedding_dim() -> int:
    """Dimensão padrão do gemini-embedding-001 (3072). Ajuste se mudar o modelo."""
    return 3072
