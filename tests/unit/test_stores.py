from chatbot.domain.stores import detect_filial_from_text, nome_da_filial, resolve_filial


def test_resolve_by_code():
    assert resolve_filial("1") == 1
    assert resolve_filial(3) == 3


def test_resolve_unknown_code_returns_none():
    assert resolve_filial("999") is None


def test_resolve_by_name_with_typo_and_accents():
    assert resolve_filial("matriz") == 1
    assert resolve_filial("MATRIZ") == 1
    assert resolve_filial("aeroporto") == 5
    assert resolve_filial("shopping norte") == 3


def test_resolve_alias():
    assert resolve_filial("cd") == 6
    assert resolve_filial("CD") == 6


def test_resolve_empty_returns_none():
    assert resolve_filial(None) is None
    assert resolve_filial("") is None


def test_detect_in_free_text():
    assert detect_filial_from_text("vendas da Matriz ontem") == 1


def test_nome_da_filial():
    assert nome_da_filial(2) == "CENTRO"
    assert nome_da_filial(None) is None
