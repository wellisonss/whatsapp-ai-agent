"""Conexões SQLAlchemy + ORM models para memória de longo prazo."""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ..core.config import get_settings


class Base(DeclarativeBase):
    pass


class UserFact(Base):
    """Fato/preferência aprendido sobre um usuário (chat_id)."""
    __tablename__ = "user_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[str] = mapped_column(String(64), index=True)
    fact: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32), default="general")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


@lru_cache
def get_engine():
    settings = get_settings()
    return create_async_engine(settings.postgres_async_dsn, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Cria tabelas se não existirem (substituível por Alembic em produção pesada)."""
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
