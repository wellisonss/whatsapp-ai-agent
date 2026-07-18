"""Entrada FastAPI: middleware, rotas, lifecycle."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.middleware import request_logger
from .api.routes import admin, health, webhook
from .core.config import get_settings
from .core.logging import get_logger, setup_logging
from .infra.db import init_db
from .integrations.waha.client import WahaClient

setup_logging()
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    log.info("api.boot", env=s.app_env)
    await init_db()
    try:
        await WahaClient().configure_webhook(s.webhook_public_url)
    except Exception as e:
        log.warning("api.boot.waha_webhook_failed", err=str(e))
    yield
    log.info("api.shutdown")


app = FastAPI(title="WhatsApp AI Agent", version="2.0.0", lifespan=lifespan)
app.middleware("http")(request_logger)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(webhook.router)
app.include_router(admin.router)
