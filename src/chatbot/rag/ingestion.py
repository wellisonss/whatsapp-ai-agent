"""Ingestão de documentos para o Qdrant.

- chunking estruturado por cabeçalhos Markdown + janelas de tamanho controlado
- idempotente: usa hash do conteúdo como id determinístico do ponto
- popula vetores dense + sparse (hybrid)
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from ..core.logging import get_logger
from ..infra.vectorstore import build_vector_store, ensure_collection
from .embeddings import embedding_dim, get_embeddings

log = get_logger(__name__)

HEADER_LEVELS = [("#", "h1"), ("##", "h2"), ("###", "h3"), ("####", "h4")]


def _chunk_markdown(text: str, source: str) -> list[Document]:
    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=HEADER_LEVELS, strip_headers=False)
    sections = splitter.split_text(text)

    rec = RecursiveCharacterTextSplitter(
        chunk_size=900,
        chunk_overlap=120,
        separators=["\n\n", "\n", ". ", "? ", "! ", " ", ""],
    )

    docs: list[Document] = []
    for sec in sections:
        for chunk in rec.split_text(sec.page_content):
            md = dict(sec.metadata)
            md["source"] = source
            md["heading_path"] = " > ".join(
                v for k in ("h1", "h2", "h3", "h4") if (v := md.get(k))
            )
            docs.append(Document(page_content=chunk, metadata=md))
    return docs


def _doc_id(d: Document) -> str:
    h = hashlib.sha256(
        f"{d.metadata.get('source','')}::{d.page_content}".encode("utf-8")
    ).hexdigest()
    return h


def ingest_directory(path: Path) -> int:
    """Indexa todos os .md sob `path`. Retorna a quantidade de chunks."""
    files = sorted(p for p in path.rglob("*.md") if p.is_file())
    if not files:
        log.warning("rag.ingest.no_files", path=str(path))
        return 0

    ensure_collection(embedding_dim())
    vs = build_vector_store(get_embeddings())

    total = 0
    docs: list[Document] = []
    ids: list[str] = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        # remove front-matter YAML, se houver
        text = re.sub(r"^---\n[\s\S]*?\n---\n", "", text, count=1)
        chunks = _chunk_markdown(text, source=str(f.relative_to(path)))
        for c in chunks:
            docs.append(c)
            ids.append(_doc_id(c))
        total += len(chunks)
        log.info("rag.ingest.file", file=str(f), chunks=len(chunks))

    if docs:
        vs.add_documents(documents=docs, ids=ids)
        log.info("rag.ingest.done", total_chunks=total)
    return total
