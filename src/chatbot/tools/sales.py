"""Tool de faturamento — wrapper sobre SalesApiClient + normalização de filtros."""
from __future__ import annotations

import json
from typing import Optional

from langchain_core.tools import tool

from ..core.logging import get_logger
from ..domain.dates import parse_date_ptbr
from ..domain.segments import suggest_channel, suggest_segment
from ..domain.stores import LOJA_CODIGO_PARA_NOME, detect_filial_from_text, resolve_filial
from ..domain.text import normalize_simple
from ..integrations.erp.sales_api import SalesApiClient

log = get_logger(__name__)

_COL_ALIAS: dict[str, str] = {
    "INDUSTRIA": "INDUSTRIA_FORNECEDOR", "FORNECEDOR": "INDUSTRIA_FORNECEDOR",
    "FABRICANTE": "INDUSTRIA_FORNECEDOR", "MARCA": "INDUSTRIA_FORNECEDOR",
    "SEGMENTO": "SEGMENTO_DESCRICAO", "CATEGORIA": "SEGMENTO_DESCRICAO",
    "VENDEDOR": "VENDEDOR_NOME", "REPRESENTANTE": "VENDEDOR_NOME",
    "CLIENTE": "NOME_CLIENTE", "COMPRADOR": "NOME_CLIENTE",
}

_ALL_LOJAS_TERMS = {
    "", "TODAS", "TODOS", "GERAL", "CONSOLIDADO",
    "TODAS AS LOJAS", "TODAS AS FILIAIS", "TODAS AS UNIDADES",
}


def _normalize_columns(colunas: Optional[str]) -> str | None:
    if not colunas:
        return colunas
    seen, out = set(), []
    for c in (x.strip().upper() for x in colunas.split(",") if x.strip()):
        m = _COL_ALIAS.get(c, c)
        if m not in seen:
            seen.add(m)
            out.append(m)
    return ",".join(out)


def _ensure_columns(colunas: Optional[str], **filtros: bool | str | None) -> str:
    base = set((colunas or "").split(",")) - {""}
    base.add("TOTAL")
    base.add("UNIDADES")
    if not filtros.get("filial_filtrada"):
        base.add("FILIAL")
    if filtros.get("segmento"):
        base.add("SEGMENTO_DESCRICAO")
    if filtros.get("canal_venda"):
        base.add("CANAL_VENDA")
    if filtros.get("vendedor_nome"):
        base.add("VENDEDOR_NOME")
    if filtros.get("nome_cliente"):
        base.add("NOME_CLIENTE")
    if filtros.get("industria"):
        base.add("INDUSTRIA_FORNECEDOR")
    if filtros.get("produto_codigo"):
        base.add("PRODUTO")
    if filtros.get("venda_identificada"):
        base.add("VENDA_IDENTIFICADA")
    return ",".join(sorted(base))


@tool
async def buscar_faturamento_itens(
    data_inicial: str,
    filial: Optional[str] = None,
    data_final: Optional[str] = None,
    vendedor_nome: Optional[str] = None,
    industria: Optional[str] = None,
    canal_venda: Optional[str] = None,
    segmento: Optional[str] = None,
    nome_cliente: Optional[str] = None,
    venda_identificada: Optional[str] = None,
    produto_codigo: Optional[str] = None,
    colunas_retorno: Optional[str] = None,
    incluir_itens: Optional[bool] = None,
) -> str:
    """Consulta faturamento/vendas (EXEMPLO) com filtros e colunas dinâmicas.

    Datas em formato dd/MM/yyyy (use get_dates para resolver expressões como 'ontem').
    Para TODAS as filiais, deixe `filial=None` ou `''` (a coluna FILIAL é incluída automaticamente).
    Para UMA filial, use o código numérico (ex.: '204') após chamar resolver_codigo_da_filial.
    `incluir_itens=None` deixa a tool decidir automaticamente se busca detalhe item-a-item."""
    filial_norm = (filial or "").strip().upper()
    quer_todas = filial is None or filial_norm in _ALL_LOJAS_TERMS

    codigo: Optional[int] = None
    if not quer_todas:
        codigo = resolve_filial(filial) or detect_filial_from_text(filial)

    di = parse_date_ptbr(data_inicial) or data_inicial
    df = parse_date_ptbr(data_final) if data_final else di

    if canal_venda:
        s = suggest_channel(canal_venda)
        if s and s != normalize_simple(canal_venda):
            canal_venda = s
    if segmento:
        s = suggest_segment(segmento)
        if s and s != normalize_simple(segmento):
            segmento = s

    cols = _ensure_columns(
        _normalize_columns(colunas_retorno),
        segmento=segmento, canal_venda=canal_venda, vendedor_nome=vendedor_nome,
        nome_cliente=nome_cliente, industria=industria, produto_codigo=produto_codigo,
        venda_identificada=venda_identificada,
        filial_filtrada=(not quer_todas and codigo is not None),
    )

    client = SalesApiClient()

    async def _call(_incluir: bool) -> str:
        return await client.fetch_report(
            data_inicial=di,
            filial=str(codigo) if (codigo is not None and not quer_todas) else "",
            data_final=df,
            vendedor_nome=vendedor_nome, industria=industria,
            canal_venda=canal_venda, segmento=segmento, nome_cliente=nome_cliente,
            venda_identificada=venda_identificada, produto_codigo=produto_codigo,
            colunas=cols, incluir_itens=_incluir,
        )

    result = await _call(incluir_itens is True)

    # Decisão automática de incluir_itens em segundo passe
    if incluir_itens is None:
        try:
            parsed = json.loads(result)
            qtd = int(parsed.get("quantidade_itens", 0))
        except Exception:
            qtd = 0
        cset = set((cols or "").split(","))
        auto = (
            ((produto_codigo or nome_cliente) and qtd <= 50)
            or (("DESCRICAO" in cset or "PRODUTO" in cset) and qtd <= 50)
            or (vendedor_nome and qtd <= 50)
        )
        if auto:
            result = await _call(True)

    # Enriquecer com nome da filial resolvida (única filial)
    if codigo is not None and not quer_todas:
        try:
            obj = json.loads(result)
            if isinstance(obj, dict):
                obj["filial_codigo_resolvido"] = codigo
                obj["filial_nome_resolvido"] = LOJA_CODIGO_PARA_NOME.get(codigo)
                result = json.dumps(obj, ensure_ascii=False)
        except Exception:
            pass
    return result
