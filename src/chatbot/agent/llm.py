"""Factory do LLM (Gemini via langchain-google-genai)."""
from __future__ import annotations

from langchain_google_genai import ChatGoogleGenerativeAI

from ..core.config import get_settings


def get_llm(temperature: float | None = None) -> ChatGoogleGenerativeAI:
    s = get_settings()
    return ChatGoogleGenerativeAI(
        model=s.llm_model,
        google_api_key=s.google_api_key,
        temperature=s.llm_temperature if temperature is None else temperature,
        convert_system_message_to_human=False,
    )
