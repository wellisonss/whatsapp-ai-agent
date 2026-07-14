"""Helpers de normalização de texto (acentos, caixa, tokenização)."""
from __future__ import annotations

import unicodedata
from typing import Optional


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def normalize_simple(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    return " ".join(str(value).upper().split())


def normalize_key(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    t = strip_accents(str(text)).upper()
    t = "".join(ch if ch.isalnum() or ch.isspace() or ch in ("/", "-") else " " for ch in t)
    return " ".join(t.split())


def tokenize(text: str) -> list[str]:
    return [t for t in text.replace("/", " ").replace("-", " ").split() if t]
