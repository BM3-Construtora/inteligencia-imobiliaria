"""Tests for src.viability — pure cost calc only (no LLM, no DB, no SINAPI)."""

from __future__ import annotations

from src.viability import (
    MCMV_FAIXAS,
    calc_cost_breakdown,
    simulate_project,
)


def test_calc_cost_breakdown_mcmv_faixa3_typical():
    """Faixa 3 typical: land 250m² @ 120k, 2 units of 60m², SINAPI 1920."""
    faixa = MCMV_FAIXAS["mcmv_faixa3"]
    units = 2
    area_total = units * faixa["unidade_area_m2"]  # 120
    preco_venda = faixa["valor_max_imovel"] * 0.95  # 380k

    out = calc_cost_breakdown(
        land_cost=120_000,
        area_total=area_total,
        sinapi_per_m2=1920.0,
        units=units,
        custo_multiplier=faixa["custo_multiplier"],
        ret_pct=faixa["ret_pct"],
        preco_venda_unidade=preco_venda,
    )

    # VGV = 2 * 380k = 760k
    assert out["vgv"] == 760_000.0
    # Investimento total within a sensible band
    assert 350_000 < out["investimento_total"] < 700_000
    # Margin should be realistic (positive, not 40%+)
    assert 5 < out["margem_liquida_pct"] < 35


def test_margin_realistic_after_calibration():
    """Typical MCMV Faixa 3 input → margin must be 12-25% (not 40%).

    TODO(prod-calibration): for Faixa 1/2 the same inputs produce negative
    margins (terreno 100k + 2x55m² + SINAPI 1920 → margem ~-3% to -0.7%).
    Either Faixa 1/2 land budget should be <80k or the cost model
    overshoots for low-tier projects. See src/viability.py MCMV_FAIXAS.
    """
    faixa = MCMV_FAIXAS["mcmv_faixa3"]
    out = calc_cost_breakdown(
        land_cost=100_000,
        area_total=2 * faixa["unidade_area_m2"],
        sinapi_per_m2=1920.0,
        units=2,
        custo_multiplier=faixa["custo_multiplier"],
        ret_pct=faixa["ret_pct"],
        preco_venda_unidade=faixa["valor_max_imovel"] * 0.95,
    )
    assert 12 <= out["margem_liquida_pct"] <= 25, (
        f"Margin {out['margem_liquida_pct']:.1f}% out of expected band"
    )


def test_no_negative_margin_in_normal_case():
    """A normal MCMV scenario should not produce a negative margin."""
    faixa = MCMV_FAIXAS["mcmv_faixa2"]
    out = calc_cost_breakdown(
        land_cost=80_000,
        area_total=2 * faixa["unidade_area_m2"],
        sinapi_per_m2=1920.0,
        units=2,
        custo_multiplier=faixa["custo_multiplier"],
        ret_pct=faixa["ret_pct"],
        preco_venda_unidade=faixa["valor_max_imovel"] * 0.95,
    )
    assert out["margem_liquida_pct"] > 0


def test_simulate_project_returns_none_for_zero_inputs():
    assert simulate_project(0, 100, "mcmv_faixa2", sinapi_cost=1920) is None
    assert simulate_project(100_000, 0, "mcmv_faixa2", sinapi_cost=1920) is None


def test_simulate_project_invalid_faixa_returns_none():
    assert simulate_project(100_000, 250, "faixa_inexistente", sinapi_cost=1920) is None
