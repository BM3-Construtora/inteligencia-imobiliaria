from types import SimpleNamespace

from src.llm_usage import estimate_cost_usd, extract_usage, _price_for


def test_price_prefix_match():
    # sufixo de versão cai no preço base do modelo
    assert _price_for("gemini-2.5-flash-002") == (0.30, 2.50)
    assert _price_for("gemini-2.0-flash") == (0.10, 0.40)
    # flash-lite não pode ser confundido com flash (prefixo mais longo primeiro)
    assert _price_for("gemini-2.5-flash-lite") == (0.10, 0.40)


def test_price_unknown_defaults_to_flash():
    assert _price_for("modelo-inexistente") == (0.30, 2.50)
    assert _price_for("") == (0.30, 2.50)


def test_estimate_cost_basic():
    # 1M input + 1M output em gemini-2.5-flash = 0.30 + 2.50
    assert estimate_cost_usd("gemini-2.5-flash", 1_000_000, 1_000_000) == 2.80


def test_estimate_cost_thinking_billed_as_output():
    base = estimate_cost_usd("gemini-2.5-flash", 0, 1_000_000, thinking_tokens=0)
    with_thinking = estimate_cost_usd("gemini-2.5-flash", 0, 1_000_000, thinking_tokens=1_000_000)
    assert with_thinking == base + 2.50


def test_embedding_is_free():
    assert estimate_cost_usd("text-embedding-004", 1_000_000, 1_000_000) == 0.0


def test_extract_usage_reads_metadata():
    resp = SimpleNamespace(usage_metadata=SimpleNamespace(
        prompt_token_count=100,
        candidates_token_count=40,
        thoughts_token_count=10,
        total_token_count=150,
    ))
    usage = extract_usage(resp)
    assert usage == {
        "prompt_tokens": 100,
        "output_tokens": 40,
        "thinking_tokens": 10,
        "total_tokens": 150,
    }


def test_extract_usage_missing_metadata():
    resp = SimpleNamespace(usage_metadata=None)
    assert extract_usage(resp)["total_tokens"] == 0


def test_extract_usage_infers_total_when_absent():
    resp = SimpleNamespace(usage_metadata=SimpleNamespace(
        prompt_token_count=100,
        candidates_token_count=40,
        thoughts_token_count=0,
        total_token_count=None,
    ))
    assert extract_usage(resp)["total_tokens"] == 140
