"""Cliente Qdrant + factory de vector store híbrida (BM25 sparse + dense)."""
from __future__ import annotations

from functools import lru_cache

from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, SparseVectorParams, VectorParams

from ..core.config import get_settings
from ..core.logging import get_logger

log = get_logger(__name__)

DENSE_VEC_NAME = "dense"
SPARSE_VEC_NAME = "sparse"


@lru_cache
def qdrant_client() -> QdrantClient:
    s = get_settings()
    return QdrantClient(url=s.qdrant_url, prefer_grpc=False)


def ensure_collection(dim: int) -> None:
    """Cria a coleção com vetores dense + sparse caso ainda não exista."""
    client = qdrant_client()
    name = get_settings().qdrant_collection
    if client.collection_exists(name):
        return
    client.create_collection(
        collection_name=name,
        vectors_config={DENSE_VEC_NAME: VectorParams(size=dim, distance=Distance.COSINE)},
        sparse_vectors_config={SPARSE_VEC_NAME: SparseVectorParams()},
    )
    log.info("qdrant.collection.created", name=name, dim=dim)


def build_vector_store(embeddings) -> QdrantVectorStore:
    """Retorna QdrantVectorStore configurada para hybrid search."""
    s = get_settings()
    return QdrantVectorStore(
        client=qdrant_client(),
        collection_name=s.qdrant_collection,
        embedding=embeddings,
        sparse_embedding=FastEmbedSparse(model_name="Qdrant/bm25"),
        retrieval_mode=RetrievalMode.HYBRID,
        vector_name=DENSE_VEC_NAME,
        sparse_vector_name=SPARSE_VEC_NAME,
    )
