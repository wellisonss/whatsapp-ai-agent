"""Modelos Pydantic para os webhooks do WAHA."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class WahaMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    id: Optional[str] = None
    timestamp: Optional[float] = None
    from_: Optional[str] = Field(default=None, alias="from")
    to: Optional[str] = None
    body: Optional[str] = None
    fromMe: bool = False
    hasMedia: bool = False
    media: Optional[dict[str, Any]] = None
    participant: Optional[str] = None


class WahaWebhook(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    event: str
    session: str
    payload: WahaMessage
    engine: Optional[str] = None
    environment: Optional[dict[str, Any]] = None
