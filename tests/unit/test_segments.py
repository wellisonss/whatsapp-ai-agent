from chatbot.domain.segments import suggest_channel, suggest_segment


def test_suggest_segment_typo():
    assert suggest_segment("ELETRONICOSS") == "ELETRONICOS"


def test_suggest_segment_exact():
    assert suggest_segment("ALIMENTOS") == "ALIMENTOS"


def test_suggest_segment_unknown():
    assert suggest_segment("zzz inexistente") is None


def test_suggest_channel():
    assert suggest_channel("varejoo") == "VAREJO"
    assert suggest_channel(None) is None
