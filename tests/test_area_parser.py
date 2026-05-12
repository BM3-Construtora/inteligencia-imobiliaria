from src.area_parser import extract_area


def test_extract_m2():
    assert extract_area("Terreno 350m² no bairro X") == 350.0
    assert extract_area("Lote 250 m2 plano") == 250.0
    assert extract_area("Área de 1.200 metros quadrados") == 1200.0


def test_extract_dimensions():
    assert extract_area("Lote 10x25 esquina") == 250.0
    assert extract_area("Terreno 12 por 30") == 360.0


def test_extract_terreno_phrase():
    assert extract_area("Terreno de 450 plano") == 450.0
    assert extract_area("Lote de 300 escriturado") == 300.0


def test_implausible_discarded():
    assert extract_area("apenas 10m²") is None
    assert extract_area("100000m²") is None
    assert extract_area("4x4") is None  # 16 m² < MIN


def test_empty():
    assert extract_area(None) is None
    assert extract_area("") is None
    assert extract_area("sem informação de área") is None
