"""Tool de cálculo de datas relativas em PT-BR."""
from __future__ import annotations

from langchain_core.tools import tool

from ..domain.dates import compute_dates


@tool
def get_dates(intervalo: str | None = None) -> list[dict[str, str]]:
    """Retorna datas/intervalos no formato dd/MM/yyyy.

    Aceita atalhos PT-BR como 'hoje', 'ontem', 'anteontem', 'ultima_terca',
    'inicio_mes', 'fim_mes', 'ultimos_7_dias', 'ultimos_15_dias', 'ultimos_30_dias' etc.
    Sem parâmetro retorna o catálogo completo de períodos."""
    return compute_dates(intervalo)
