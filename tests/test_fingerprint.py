from src.fingerprint import compute_fingerprint


def test_same_property_diff_portal():
    a = {"neighborhood": "Jd. Cascata", "address": "Rua Bahia 250",
         "total_area": 360, "street": "Rua Bahia", "number": "250"}
    b = {"neighborhood": "Jardim Cascata", "address": "R. Bahia, 250",
         "total_area": 372, "street": None, "number": None}
    assert compute_fingerprint(a) == compute_fingerprint(b)


def test_diff_number_diff_fingerprint():
    a = {"neighborhood": "Cascata", "address": "Rua X 100", "total_area": 300}
    b = {"neighborhood": "Cascata", "address": "Rua X 200", "total_area": 300}
    assert compute_fingerprint(a) != compute_fingerprint(b)


def test_returns_none_without_street():
    assert compute_fingerprint({"neighborhood": "Cascata", "total_area": 300}) is None


def test_missing_area_uses_x_bucket():
    a = {"neighborhood": "Cascata", "address": "Rua Y 50", "total_area": None}
    fp = compute_fingerprint(a)
    assert fp is not None
    assert fp.endswith("|x")
