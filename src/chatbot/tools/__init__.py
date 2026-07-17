"""Tools expostas ao agente (LangChain @tool)."""
from .dates import get_dates
from .knowledge import retrieve_knowledge
from .sales import buscar_faturamento_itens
from .stores import resolver_codigo_da_filial

ALL_TOOLS = [
    resolver_codigo_da_filial,
    buscar_faturamento_itens,
    get_dates,
    retrieve_knowledge,
]

__all__ = ["ALL_TOOLS", "buscar_faturamento_itens", "resolver_codigo_da_filial",
           "get_dates", "retrieve_knowledge"]
