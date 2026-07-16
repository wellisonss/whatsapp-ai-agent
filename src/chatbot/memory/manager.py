"""Memória de longo prazo segmentada por chat_id (Postgres).

Conceitualmente:
- *Session memory*: histórico curto da conversa → fica no checkpointer do LangGraph.
- *Long-term memory*: fatos/preferências que devem ser lembrados entre sessões → fica aqui.
"""
from __future__ import annotations

from sqlalchemy import select

from ..core.logging import get_logger
from ..infra.db import UserFact, get_sessionmaker

log = get_logger(__name__)


class MemoryManager:
    def __init__(self) -> None:
        self.sm = get_sessionmaker()

    async def add_facts(self, chat_id: str, facts: list[str], category: str = "general") -> int:
        if not facts:
            return 0
        async with self.sm() as s:
            existing = {
                f.fact for f in (
                    await s.execute(
                        select(UserFact).where(UserFact.chat_id == chat_id).where(UserFact.category == category)
                    )
                ).scalars()
            }
            new_rows = [UserFact(chat_id=chat_id, fact=f, category=category)
                        for f in facts if f and f not in existing]
            s.add_all(new_rows)
            await s.commit()
            log.info("memory.add", chat_id=chat_id, added=len(new_rows), category=category)
            return len(new_rows)

    async def get_facts(self, chat_id: str, limit: int = 25) -> list[str]:
        async with self.sm() as s:
            rows = (
                await s.execute(
                    select(UserFact)
                    .where(UserFact.chat_id == chat_id)
                    .order_by(UserFact.updated_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
            return [r.fact for r in rows]

    async def render_for_prompt(self, chat_id: str) -> str:
        facts = await self.get_facts(chat_id)
        if not facts:
            return ""
        return "Fatos lembrados sobre este usuário:\n" + "\n".join(f"- {f}" for f in facts)
