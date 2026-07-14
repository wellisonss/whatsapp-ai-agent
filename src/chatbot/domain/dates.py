"""Cálculo de datas relativas em PT-BR (port da get_dates antiga)."""
from __future__ import annotations

import re
from datetime import date, timedelta

WEEKDAYS_MAP: dict[str, int] = {
    "segunda": 0, "terca": 1, "quarta": 2, "quinta": 3,
    "sexta": 4, "sabado": 5, "domingo": 6,
}


def format_ddmmyyyy(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def parse_ddmmyyyy(s: str) -> date | None:
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", s.strip())
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _last_weekday(today: date, weekday: int) -> date:
    delta = (today.weekday() - weekday + 7) % 7
    return today - timedelta(days=7 if delta == 0 else delta)


def compute_dates(intervalo: str | None = None, today: date | None = None) -> list[dict[str, str]]:
    """Retorna lista de períodos no formato esperado pelo agente.

    Suporta atalhos PT-BR ('hoje', 'ontem', 'ultima_terca', 'ultimos_15_dias' etc).
    Quando intervalo=None, retorna o catálogo completo.
    """
    today = today or date.today()
    wd = today.weekday()

    sw = today - timedelta(days=wd)
    ew = sw + timedelta(days=6)
    slw = sw - timedelta(days=7)
    elw = sw - timedelta(days=1)
    sm = today.replace(day=1)
    if sm.month < 12:
        nm = sm.replace(month=sm.month + 1, day=1)
    else:
        nm = sm.replace(year=sm.year + 1, month=1, day=1)
    em = nm - timedelta(days=1)
    elm = sm - timedelta(days=1)
    slm = elm.replace(day=1)
    sy = today.replace(month=1, day=1)
    ey = today.replace(month=12, day=31)

    catalog = [
        {"periodo": "Data atual", "data": format_ddmmyyyy(today)},
        {"periodo": "Anteontem", "data": format_ddmmyyyy(today - timedelta(days=2))},
        {"periodo": "Ontem", "data": format_ddmmyyyy(today - timedelta(days=1))},
        {"periodo": "Início da semana atual (Seg)", "data": format_ddmmyyyy(sw)},
        {"periodo": "Fim da semana atual (Dom)", "data": format_ddmmyyyy(ew)},
        {"periodo": "Início da semana anterior (Seg)", "data": format_ddmmyyyy(slw)},
        {"periodo": "Fim da semana anterior (Dom)", "data": format_ddmmyyyy(elw)},
        {"periodo": "Início do Mês atual", "data": format_ddmmyyyy(sm)},
        {"periodo": "Fim do Mês atual", "data": format_ddmmyyyy(em)},
        {"periodo": "Início do Mês anterior", "data": format_ddmmyyyy(slm)},
        {"periodo": "Fim do Mês anterior", "data": format_ddmmyyyy(elm)},
        {"periodo": "Início do Ano atual", "data": format_ddmmyyyy(sy)},
        {"periodo": "Fim do Ano atual", "data": format_ddmmyyyy(ey)},
    ]
    for n in (7, 15, 30, 90, 365):
        catalog.append({
            "periodo": f"Últimos {n} dias",
            "data": f"{format_ddmmyyyy(today - timedelta(days=n))} - {format_ddmmyyyy(today)}",
        })
    for name, idx in WEEKDAYS_MAP.items():
        catalog.append({
            "periodo": (f"Última {name.capitalize()}" if name not in ("domingo", "sabado")
                        else f"Último {name.capitalize()}"),
            "data": format_ddmmyyyy(_last_weekday(today, idx)),
        })

    if not intervalo:
        return catalog

    raw = intervalo.strip().lower()
    norm = (raw.replace("últimos", "ultimos").replace("último", "ultimo")
              .replace("á", "a").replace("ú", "u").replace("ã", "a").replace("â", "a")
              .replace("é", "e").replace("ê", "e").replace("í", "i")
              .replace("ó", "o").replace("ô", "o").replace("ç", "c")
              .replace(" ", "_"))

    m = re.match(r"^ultimos_?(\d+)_?dias$", norm)
    if m:
        qtd = int(m.group(1))
        if qtd > 0:
            return [{
                "periodo": f"Últimos {qtd} dias",
                "data": f"{format_ddmmyyyy(today - timedelta(days=qtd))} - {format_ddmmyyyy(today)}",
            }]

    alias = {
        "hoje": "Data atual", "anteontem": "Anteontem", "ontem": "Ontem",
        "inicio_semana": "Início da semana atual (Seg)",
        "fim_semana": "Fim da semana atual (Dom)",
        "inicio_mes": "Início do Mês atual", "fim_mes": "Fim do Mês atual",
        "inicio_ano": "Início do Ano atual", "fim_ano": "Fim do Ano atual",
        "inicio_semana_anterior": "Início da semana anterior (Seg)",
        "fim_semana_anterior": "Fim da semana anterior (Dom)",
        "inicio_mes_anterior": "Início do Mês anterior",
        "fim_mes_anterior": "Fim do Mês anterior",
        "ultimos_7_dias": "Últimos 7 dias", "ultimos_15_dias": "Últimos 15 dias",
        "ultimos_30_dias": "Últimos 30 dias",
        "ultimos_90_dias": "Últimos 90 dias", "ultimos_365_dias": "Últimos 365 dias",
    }
    for name in WEEKDAYS_MAP:
        alias[f"ultima_{name}"] = (
            f"Última {name.capitalize()}" if name not in ("domingo", "sabado")
            else f"Último {name.capitalize()}"
        )
    target = alias.get(norm)
    if not target:
        return []
    return [p for p in catalog if p["periodo"] == target]


def parse_date_ptbr(text: str | None, today: date | None = None) -> str | None:
    """Converte 'hoje'/'ontem'/'última terça'/dd-mm para dd/mm/yyyy ou retorna None."""
    if not text:
        return None
    res = compute_dates(text, today=today)
    if res:
        d = res[0]["data"]
        if " - " in d:
            return d.split(" - ")[0]
        return d
    parsed = parse_ddmmyyyy(text)
    return format_ddmmyyyy(parsed) if parsed else None
