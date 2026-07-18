"""Cria tabelas do Postgres (memória de longo prazo)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from chatbot.core.logging import get_logger, setup_logging  # noqa: E402
from chatbot.infra.db import init_db  # noqa: E402


async def main() -> None:
    setup_logging()
    log = get_logger(__name__)
    await init_db()
    log.info("migrate.done")


if __name__ == "__main__":
    asyncio.run(main())
