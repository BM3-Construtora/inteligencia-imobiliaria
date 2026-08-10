"""Passe de extração via LLM sobre snippets do Diário Oficial (DOM-MAR).

Os coletores do DOM capturam o `snippet`/`raw_snippet` mas o regex não extrai
campos estruturados de prosa (requerente, bairro afetado, nome de loteamento).
Este módulo roda um Gemini structured-output sobre os snippets já persistidos e
preenche os campos vazios. Reutiliza src/llm.py (com telemetria em llm_usage).

Uso: python -m src.main dom-extract <tabela> [limit] [--dry-run]
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from src.db import get_client
from src.llm import _generate, _parse_json, GEMINI_API_KEY

logger = logging.getLogger(__name__)


def _prompt_plano_diretor(snippet: str) -> str:
    return (
        "Trecho do Diário Oficial de Marília-SP sobre plano diretor / zoneamento.\n"
        "Extraia, SOMENTE se explícito no texto, o bairro/loteamento afetado por "
        "mudança de zoneamento ou uso do solo (upzoning).\n\n"
        f"TRECHO:\n{snippet[:1200]}\n\n"
        'Responda APENAS JSON: {"upzoning_bairro": "<nome do bairro afetado, ou null>"}. '
        "Se o trecho não indicar um bairro específico com mudança de zoneamento, use null."
    )


def _prompt_parcelamento(snippet: str) -> str:
    return (
        "Trecho do Diário Oficial de Marília-SP sobre parcelamento de solo "
        "(loteamento/desmembramento).\n"
        "Extraia o NOME do empreendimento e o bairro, SOMENTE se explícitos.\n\n"
        f"TRECHO:\n{snippet[:1200]}\n\n"
        'Responda APENAS JSON: {"titulo": "<nome do loteamento, ou null>", '
        '"neighborhood": "<bairro, ou null>"}. '
        "Não invente: se o nome não estiver claro no texto, use null."
    )


# Config por tabela: coluna do snippet, campo-filtro (nulo = precisa extrair),
# campos-alvo a preencher, e o prompt.
SPECS: dict[str, dict[str, Any]] = {
    "plano_diretor_signals": {
        "snippet_col": "raw_snippet",
        "filter_col": "upzoning_bairro",
        "targets": ["upzoning_bairro"],
        "prompt": _prompt_plano_diretor,
    },
    "parcelamento_solo_marilia": {
        "snippet_col": "snippet",
        "filter_col": "titulo",
        "targets": ["titulo", "neighborhood"],
        "prompt": _prompt_parcelamento,
    },
}


def _clean(value: Any) -> str | None:
    """Normaliza a saída do LLM: descarta null/vazio/'null' textual."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("null", "none", "n/a", "-"):
        return None
    return s


def run_dom_extract(table: str, limit: int = 50, dry_run: bool = False) -> dict[str, int]:
    """Preenche campos vazios de uma tabela DOM via LLM sobre o snippet."""
    stats = {"scanned": 0, "extracted": 0, "updated": 0, "skipped_no_llm": 0}

    if table not in SPECS:
        raise SystemExit(f"Tabela não suportada: {table}. Opções: {list(SPECS)}")
    if not GEMINI_API_KEY:
        logger.error("[dom_extract] GEMINI_API_KEY ausente — nada a fazer")
        stats["skipped_no_llm"] = 1
        return stats

    spec = SPECS[table]
    snippet_col: str = spec["snippet_col"]
    filter_col: str = spec["filter_col"]
    targets: list[str] = spec["targets"]
    prompt_fn: Callable[[str], str] = spec["prompt"]

    db = get_client()
    rows = (
        db.table(table)
        .select(f"id, {snippet_col}, {', '.join(targets)}")
        .is_(filter_col, "null")
        .not_.is_(snippet_col, "null")
        .limit(limit)
        .execute()
    ).data or []

    logger.info(f"[dom_extract] {table}: {len(rows)} linha(s) sem {filter_col}")

    for row in rows:
        stats["scanned"] += 1
        snippet = row.get(snippet_col) or ""
        if len(snippet) < 20:
            continue

        parsed = _parse_json(_generate(prompt_fn(snippet), max_tokens=200, task=f"dom_extract_{table}") or "")
        if isinstance(parsed, list):
            parsed = parsed[0] if parsed and isinstance(parsed[0], dict) else None
        if not isinstance(parsed, dict):
            continue

        update = {}
        for t in targets:
            if not row.get(t):
                val = _clean(parsed.get(t))
                if val:
                    update[t] = val
        if not update:
            continue

        stats["extracted"] += 1
        if dry_run:
            logger.info(f"[dom_extract] (dry) id={row['id']} -> {update}")
            continue
        try:
            db.table(table).update(update).eq("id", row["id"]).execute()
            stats["updated"] += 1
        except Exception:
            logger.exception(f"[dom_extract] update falhou id={row['id']}")

    logger.info(f"[dom_extract] {table} done: {stats}")
    return stats
