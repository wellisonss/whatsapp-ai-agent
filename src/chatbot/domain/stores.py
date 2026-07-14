"""Catálogo de unidades/filiais + resolução fuzzy nome <-> código.

>>> ADAPTE ESTE ARQUIVO À SUA REALIDADE <<<
Os dados abaixo são apenas um EXEMPLO genérico. Substitua `LOJA_CODIGO_PARA_NOME`
pelos códigos e nomes reais das suas unidades. Ajuste `_ALIASES` (apelidos comuns
com erro de digitação/acentuação) e `_STOPWORDS` (palavras que não ajudam a
distinguir uma unidade da outra). Toda a lógica de resolução fuzzy é genérica.
"""
from __future__ import annotations

import difflib
from collections import defaultdict
from typing import Optional

from .text import normalize_key, tokenize

# EXEMPLO — troque pelos códigos/nomes reais das suas unidades.
LOJA_CODIGO_PARA_NOME: dict[int, str] = {
    1: "MATRIZ",
    2: "CENTRO",
    3: "SHOPPING NORTE",
    4: "SHOPPING SUL",
    5: "AEROPORTO",
    6: "CENTRO DE DISTRIBUIÇÃO",
}

_NOME_NORMALIZADO_PARA_CODIGO: dict[str, int] = {
    normalize_key(nome) or "": codigo for codigo, nome in LOJA_CODIGO_PARA_NOME.items()
}

# Apelidos / grafias alternativas que o usuário pode digitar (EXEMPLO).
_ALIASES: dict[str, int] = {
    "CD": 6, "CENTRO DISTRIBUICAO": 6,
    "SHOPPING N": 3, "SHOPPING S": 4,
}

# Palavras que aparecem em muitos nomes e não ajudam a distinguir (EXEMPLO).
_STOPWORDS = {"DE", "DO", "DA", "DAS", "DOS", "SHOPPING", "CENTRO", "DISTRIBUICAO"}

_KEYWORD_TO_CODES: dict[str, list[int]] = defaultdict(list)
for _cod, _nome in LOJA_CODIGO_PARA_NOME.items():
    for _tok in tokenize(normalize_key(_nome) or ""):
        if _tok in _STOPWORDS:
            continue
        if _cod not in _KEYWORD_TO_CODES[_tok]:
            _KEYWORD_TO_CODES[_tok].append(_cod)


def _score(query: str, candidate: str) -> float:
    if query == candidate:
        return 1.0
    score = 0.0
    if query in candidate or candidate in query:
        score = 0.9
    qt = [t for t in tokenize(query) if t not in _STOPWORDS]
    ct = [t for t in tokenize(candidate) if t not in _STOPWORDS]
    if qt:
        inter = sum(1 for t in qt if t in ct)
        score = max(score, 0.6 + 0.3 * (inter / len(qt)))
    sim = difflib.SequenceMatcher(a=query, b=candidate).ratio()
    score = max(score, 0.5 + 0.5 * sim * 0.8)
    return min(score, 0.99)


def resolve_filial(value: Optional[str | int]) -> Optional[int]:
    """Recebe código numérico OU nome (com erros/abreviações) e devolve o código.

    Retorna None quando a entrada é vazia/ambígua/desconhecida.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value if value in LOJA_CODIGO_PARA_NOME else None
    s = str(value).strip()
    if not s:
        return None
    if s.isdigit():
        cod = int(s)
        return cod if cod in LOJA_CODIGO_PARA_NOME else None

    norm = normalize_key(s) or ""
    if norm in _ALIASES:
        return _ALIASES[norm]
    if norm in _NOME_NORMALIZADO_PARA_CODIGO:
        return _NOME_NORMALIZADO_PARA_CODIGO[norm]

    best_cod, best_score = None, 0.0
    for codigo, nome in LOJA_CODIGO_PARA_NOME.items():
        sc = _score(norm, normalize_key(nome) or "")
        if sc > best_score or (sc == best_score and best_cod is not None and codigo < best_cod):
            best_score, best_cod = sc, codigo
    return best_cod if best_score >= 0.85 else None


def detect_filial_from_text(text: Optional[str]) -> Optional[int]:
    """Tenta achar uma filial mencionada num texto livre do usuário."""
    return resolve_filial(text)


def nome_da_filial(codigo: Optional[int]) -> Optional[str]:
    if codigo is None:
        return None
    return LOJA_CODIGO_PARA_NOME.get(codigo)


def listar_filiais() -> str:
    return ", ".join(f"{c}: {n}" for c, n in sorted(LOJA_CODIGO_PARA_NOME.items()))
