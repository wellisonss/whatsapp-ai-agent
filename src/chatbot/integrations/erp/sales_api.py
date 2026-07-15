"""Cliente de EXEMPLO para uma API REST de relatório de vendas.

Este módulo demonstra o padrão de "tool que consulta um sistema externo"
(ERP, CRM, data warehouse etc.): monta filtros, faz GET com retry exponencial
e timeout, e agrega o JSON de resposta em somas/agrupamentos prontos para o LLM.

Adapte `fetch_report` e os parâmetros ao contrato da SUA API. O endpoint e o
"modo" vêm da configuração (`ERP_SALES_URL`, `ERP_SALES_MODE`).
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Optional
from urllib.parse import urlencode

import aiohttp

from ...core.config import get_settings
from ...core.exceptions import ErpError
from ...core.logging import get_logger
from ...domain.stores import LOJA_CODIGO_PARA_NOME, listar_filiais, resolve_filial

log = get_logger(__name__)

_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
CHAVES_DE_AGRUPAMENTO = [
    "FILIAL", "VENDEDOR_NOME", "NOME_CLIENTE", "DESCRICAO",
    "SEGMENTO_DESCRICAO", "INDUSTRIA_FORNECEDOR", "CANAL_VENDA", "ID_VENDA",
]

# Limites para evitar explosão de tokens no contexto do LLM
_MAX_GROUP_ENTRIES = 30   # top-N por grupo em somas_por_grupo
_MAX_ITENS = 50           # máximo de itens brutos quando incluir_itens=True


def _parse_number(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if not isinstance(val, str):
        return None
    s = val.strip()
    if not s:
        return None
    s = re.sub(r"[^\d,.\-]+", "", s)
    if s.count(",") > 1 and s.count(".") == 0:
        s = s.replace(",", "")
    elif s.count(".") > 1 and s.count(",") == 0:
        s = s.replace(".", "")
    elif s.count(",") == 1 and s.count(".") >= 1 and s.rfind(",") > s.rfind("."):
        s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _ticket_medio(data_list: list[dict], chaves: list[str]) -> dict:
    grupos: dict[str, dict[str, dict[str, float]]] = {}
    for item in data_list:
        for chave in chaves:
            v = item.get(chave)
            if v is None:
                continue
            cv = str(v).strip().upper()
            grupos.setdefault(cv, {})
            vid = item.get("ID_VENDA")
            if vid is None:
                continue
            vid = str(vid).strip()
            grupos[cv].setdefault(vid, {"TOTAL_VENDA": 0.0})
            grupos[cv][vid]["TOTAL_VENDA"] += _parse_number(item.get("TOTAL")) or 0.0

    n = sum(len(v) for v in grupos.values())
    total = sum(t["TOTAL_VENDA"] for g in grupos.values() for t in g.values())
    if n == 0 or total <= 0:
        return {"ticket_medio_total": 0.0, "ticket_medio_por_chave": {}}
    return {
        "ticket_medio_total": total / n,
        "ticket_medio_por_chave": {
            k: (sum(t["TOTAL_VENDA"] for t in v.values()) / len(v) if v else 0.0)
            for k, v in grupos.items()
        },
    }


class SalesApiClient:
    def __init__(self, base_url: str | None = None, timeout: float = 30.0, retries: int = 3) -> None:
        self.base_url = base_url or get_settings().erp_sales_url
        self.timeout = timeout
        self.retries = retries

    async def fetch_report(
        self,
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
        colunas: Optional[str] = None,
        incluir_itens: bool = False,
    ) -> str:
        if not _DATE_RE.match((data_inicial or "").strip()):
            return "Formato de data inicial inválido. Use dd/MM/yyyy."
        if data_final and not _DATE_RE.match(data_final.strip()):
            return "Formato de data final inválido. Use dd/MM/yyyy."

        filial_codigo: Optional[int] = None
        if filial and str(filial).strip():
            filial_codigo = resolve_filial(filial)
            if filial_codigo is None:
                return f"Filial inválida. Unidades disponíveis: {listar_filiais()}"

        params: dict[str, str] = {
            "mode": get_settings().erp_sales_mode,
            "data_inicial": data_inicial.strip(),
        }
        if filial_codigo is not None:
            params["filial"] = str(filial_codigo)
        for k, v in dict(
            data_final=data_final, vendedor_nome=vendedor_nome, industria=industria,
            canal_venda=canal_venda, segmento=segmento, nome_cliente=nome_cliente,
            venda_identificada=venda_identificada, produto_codigo=produto_codigo,
        ).items():
            if v:
                params[k] = v.strip()

        cols = {c.strip() for c in (colunas or "").split(",") if c.strip()}
        if filial_codigo is None:
            cols.add("FILIAL")
        if cols:
            params["colunas"] = ",".join(cols)

        payload = await self._request(params)

        data_list = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
        if not data_list:
            return "Nenhum item de venda encontrado para os filtros e data solicitados."

        somas: dict[str, float] = {}
        somas_por_grupo: dict[str, dict[str, dict[str, float]]] = {}
        qtd_itens = 0
        for item in data_list:
            if not isinstance(item, dict):
                continue
            qtd_itens += 1
            for k, v in item.items():
                num = _parse_number(v)
                if num is not None:
                    somas[k] = somas.get(k, 0.0) + num
            total_item = _parse_number(item.get("TOTAL")) or 0.0
            unidades_item = _parse_number(item.get("UNIDADES")) or 0.0
            for grupo in CHAVES_DE_AGRUPAMENTO:
                if grupo not in item:
                    continue
                cv = str(item.get(grupo, "")).strip().upper()
                if not cv:
                    continue
                somas_por_grupo.setdefault(grupo, {})
                somas_por_grupo[grupo].setdefault(cv, {"TOTAL": 0.0, "UNIDADES": 0.0, "qtd_itens": 0})
                somas_por_grupo[grupo][cv]["TOTAL"] += total_item
                somas_por_grupo[grupo][cv]["UNIDADES"] += unidades_item
                somas_por_grupo[grupo][cv]["qtd_itens"] += 1

        # Top-K por grupo: mantém só os _MAX_GROUP_ENTRIES maiores por TOTAL
        somas_por_grupo_truncado: dict[str, Any] = {}
        for grupo, entries in somas_por_grupo.items():
            if len(entries) <= _MAX_GROUP_ENTRIES:
                somas_por_grupo_truncado[grupo] = entries
            else:
                top = sorted(entries.items(), key=lambda x: x[1].get("TOTAL", 0), reverse=True)
                somas_por_grupo_truncado[grupo] = {
                    k: v for k, v in top[:_MAX_GROUP_ENTRIES]
                }
                somas_por_grupo_truncado[f"_{grupo}_total_entradas"] = len(entries)

        # Remove somas numéricas zeradas (não trazem informação)
        somas_filtradas = {k: v for k, v in somas.items() if v}

        out: dict[str, Any] = {
            "somas_numericas": somas_filtradas,
            "somas_por_grupo": somas_por_grupo_truncado,
            "quantidade_itens": qtd_itens,
        }
        if filial_codigo is not None:
            out["filial_codigo_resolvido"] = filial_codigo
            out["filial_nome_resolvido"] = LOJA_CODIGO_PARA_NOME.get(filial_codigo)
        if incluir_itens:
            # Top-K itens por TOTAL para limitar tokens
            itens_ordenados = sorted(
                data_list, key=lambda x: _parse_number(x.get("TOTAL")) or 0, reverse=True
            )
            out["itens"] = itens_ordenados[:_MAX_ITENS]
            if len(data_list) > _MAX_ITENS:
                out["itens_truncados"] = True
                out["itens_total_real"] = len(data_list)
        if "ID_VENDA" in (cols or set()) and data_list:
            try:
                out["ticket_medio"] = _ticket_medio(data_list, CHAVES_DE_AGRUPAMENTO)
            except Exception as e:  # pragma: no cover
                out["ticket_medio_erro"] = str(e)

        # Serialização compacta (sem espaços) reduz ~15-20% dos tokens
        return json.dumps(out, ensure_ascii=False, separators=(",", ":"))

    async def _request(self, params: dict[str, str]) -> Any:
        backoff = 1.0
        text_preview = ""
        log.debug("erp.sales.url", url=f"{self.base_url}?{urlencode(params)}")
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
            for attempt in range(1, self.retries + 1):
                try:
                    async with session.get(self.base_url, params=params) as resp:
                        log.info("erp.sales.request", url=str(resp.url), attempt=attempt)
                        text_preview = await resp.text()
                        resp.raise_for_status()
                        return await resp.json(content_type=None)
                except aiohttp.ClientError as e:
                    if attempt == self.retries:
                        raise ErpError(f"Falha ao consultar ERP: {e}; preview={text_preview[:200]}") from e
                    await asyncio.sleep(backoff)
                    backoff *= 2
        raise ErpError("Falha sem motivo aparente ao consultar ERP")
