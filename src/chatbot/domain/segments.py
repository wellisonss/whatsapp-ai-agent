"""Segmentos e canais conhecidos + sugestão fuzzy.

>>> ADAPTE ESTAS LISTAS À SUA REALIDADE <<<
Os valores abaixo são apenas EXEMPLOS. Coloque aqui os segmentos/categorias de
produto e os canais de venda usados pela sua empresa. A sugestão fuzzy corrige
pequenos erros de digitação do usuário automaticamente.
"""
from __future__ import annotations

import difflib
from typing import Optional

from .text import normalize_simple

# EXEMPLO — troque pelas categorias/segmentos reais dos seus produtos.
KNOWN_SEGMENTS: list[str] = [
    "ELETRONICOS", "VESTUARIO", "ALIMENTOS",
    "BEBIDAS", "CASA E DECORACAO", "SERVICOS",
]

# EXEMPLO — troque pelos seus canais de venda.
KNOWN_CHANNELS: list[str] = ["VAREJO", "ECOMMERCE", "ATACADO"]


def _suggest(value: Optional[str], universe: list[str]) -> Optional[str]:
    norm = normalize_simple(value)
    if not norm:
        return None
    if norm in universe:
        return norm
    matches = difflib.get_close_matches(norm, universe, n=1, cutoff=0.8)
    return matches[0] if matches else None


def suggest_segment(value: Optional[str]) -> Optional[str]:
    return _suggest(value, KNOWN_SEGMENTS)


def suggest_channel(value: Optional[str]) -> Optional[str]:
    return _suggest(value, KNOWN_CHANNELS)
