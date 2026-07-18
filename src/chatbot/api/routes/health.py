"""Healthchecks."""
from __future__ import annotations

from fastapi import APIRouter

from ...infra.redis_client import get_redis

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/health/deep")
async def health_deep() -> dict:
    out = {"status": "ok"}
    try:
        await get_redis().ping()
        out["redis"] = "ok"
    except Exception as e:
        out["redis"] = f"err:{e}"
        out["status"] = "degraded"
    return out
