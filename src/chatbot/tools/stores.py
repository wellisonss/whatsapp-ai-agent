"""Tool de resolução de filial (nome → código)."""
from __future__ import annotations

from langchain_core.tools import tool

from ..domain.stores import resolve_filial


@tool
def resolver_codigo_da_filial(filial: str) -> int | None:
    """Converte um nome (com erros, abreviações ou acentos) ou código de filial/unidade para o código numérico oficial.

    Use sempre que o usuário mencionar UMA filial específica (ex.: 'Matriz', 'Shopping Norte').
    Retorna None se não conseguir resolver com confiança suficiente — peça confirmação ao usuário."""
    return resolve_filial(filial)
