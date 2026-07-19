from chatbot.domain.text import normalize_key, normalize_simple, strip_accents


def test_strip_accents():
    assert strip_accents("São Paulo") == "Sao Paulo"


def test_normalize_simple():
    assert normalize_simple("  loja   NORTE ") == "LOJA NORTE"
    assert normalize_simple(None) is None


def test_normalize_key():
    assert normalize_key("São Paulo Centro") == "SAO PAULO CENTRO"
    assert normalize_key("D'Água") == "D AGUA"
