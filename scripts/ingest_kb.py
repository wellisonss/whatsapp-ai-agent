"""(Re)indexa a base de conhecimento Markdown para o Qdrant.

Uso:
    docker compose exec api python -m scripts.ingest_kb [--path data/knowledge]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# garante que /app/src esteja no path quando rodando localmente
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from chatbot.core.logging import get_logger, setup_logging  # noqa: E402
from chatbot.rag.ingestion import ingest_directory  # noqa: E402


def main() -> int:
    setup_logging()
    log = get_logger(__name__)
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="data/knowledge", help="diretório com .md")
    args = parser.parse_args()

    p = Path(args.path)
    if not p.exists():
        log.error("ingest.path_not_found", path=str(p))
        return 1

    total = ingest_directory(p)
    log.info("ingest.done", total=total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
