"""Teste smoke da rota /webhook/waha — não invoca o agente.

Mocka enqueue para evitar dependência de Redis em CI local.
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

from fastapi.testclient import TestClient


def _client():
    # Import tardio para não inicializar Postgres/Waha em import
    from chatbot.api.routes import webhook
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(webhook.router)
    return TestClient(app)


def test_ignores_non_message_event():
    c = _client()
    r = c.post("/webhook/waha", json={"event": "session.status", "session": "default", "payload": {}})
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


def test_queues_message():
    async def fake_enqueue(_):  # noqa
        return True

    with patch("chatbot.api.routes.webhook.enqueue", side_effect=fake_enqueue):
        c = _client()
        body = {
            "event": "message",
            "session": "default",
            "payload": {
                "id": "msg1",
                "from": "5599999999@c.us",
                "body": "olá",
                "fromMe": False,
            },
        }
        r = c.post("/webhook/waha", json=body)
    assert r.status_code == 200
    assert r.json()["status"] == "queued"


def test_ignores_fromMe():
    c = _client()
    body = {
        "event": "message",
        "session": "default",
        "payload": {"id": "x", "from": "x@c.us", "body": "oi", "fromMe": True},
    }
    r = c.post("/webhook/waha", json=body)
    assert r.json()["status"] == "ignored"
