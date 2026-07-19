from datetime import date

from chatbot.domain.dates import compute_dates, parse_date_ptbr


T = date(2026, 4, 28)  # terça-feira


def test_today():
    res = compute_dates("hoje", today=T)
    assert res == [{"periodo": "Data atual", "data": "28/04/2026"}]


def test_yesterday():
    res = compute_dates("ontem", today=T)
    assert res[0]["data"] == "27/04/2026"


def test_last_n_days_dynamic():
    res = compute_dates("ultimos_15_dias", today=T)
    assert res[0]["periodo"] == "Últimos 15 dias"
    assert res[0]["data"] == "13/04/2026 - 28/04/2026"


def test_last_friday():
    res = compute_dates("ultima_sexta", today=T)
    assert res[0]["data"] == "24/04/2026"


def test_parse_date_ptbr_passthrough():
    assert parse_date_ptbr("28/04/2026", today=T) == "28/04/2026"


def test_parse_date_ptbr_alias():
    assert parse_date_ptbr("ontem", today=T) == "27/04/2026"


def test_parse_date_ptbr_unknown():
    assert parse_date_ptbr("xpto", today=T) is None
