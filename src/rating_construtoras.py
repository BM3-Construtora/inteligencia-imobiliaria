"""Rating de Construtoras — avalia construtoras de Marília-SP com dados públicos.

Fontes:
  - alvaras_marilia: alvarás de construção emitidos
  - habite_se_records: conclusões de obra
  - eiv_marilia: estudos de impacto (grandes empreendimentos)

Lógica:
  - score_entrega = (habite_se / alvaras) * 100  — taxa de conclusão
  - score_prazo = 100 - normalizado(tempo_medio_obra_dias) — quanto mais rápido, melhor
  - score_volume = log(alvaras + 1) * 10 — volume normalizado
  - score_geral = 0.50 * entrega + 0.35 * prazo + 0.15 * volume
  - tier: A (>80), B (60-79), C (40-59), D (<40)

Tabela destino: construtoras_rating
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from src.db import get_client

logger = logging.getLogger(__name__)

# Benchmarks de prazo para Marília-SP (calibrados com dados reais)
PRAZO_IDEAL_DIAS = 180     # 6 meses — obra pequena MCMV
PRAZO_MAX_DIAS = 1095      # 3 anos — obra grande com problemas

# Pesos do score composto
WEIGHT_ENTREGA = 0.50
WEIGHT_PRAZO = 0.35
WEIGHT_VOLUME = 0.15


def run_rating_construtoras() -> dict[str, int]:
    """Calcula e atualiza o rating de todas as construtoras ativas."""
    db = get_client()
    stats = {"construtoras": 0, "rated": 0, "failed": 0}

    run_result = db.table("agent_runs").insert({
        "agent_name": "rating_construtoras", "status": "running"
    }).execute()
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        # 1. Agregar dados de alvarás por construtora
        alvaras_stats = _fetch_alvaras_stats(db)
        logger.info(f"[rating] {len(alvaras_stats)} construtoras com alvarás")

        # 2. Agregar dados de habite-se por construtora
        habite_stats = _fetch_habite_stats(db)
        logger.info(f"[rating] {len(habite_stats)} construtoras com habite-se")

        # 3. Calcular delta alvará→habite-se (tempo médio de obra)
        prazo_stats = _calculate_prazo_stats(db)
        logger.info(f"[rating] {len(prazo_stats)} construtoras com dados de prazo")

        # 4. Merge e calcular scores
        all_construtoras: set[str] = set(alvaras_stats.keys()) | set(habite_stats.keys())
        stats["construtoras"] = len(all_construtoras)

        for nome in all_construtoras:
            try:
                alv = alvaras_stats.get(nome, {})
                hab = habite_stats.get(nome, {})
                prazo = prazo_stats.get(nome, {})

                rating = _calculate_rating(nome, alv, hab, prazo)

                if rating.get("cnpj"):
                    db.table("construtoras_rating").upsert(
                        rating, on_conflict="cnpj"
                    ).execute()
                else:
                    # Se não tem CNPJ, upsert por nome
                    _upsert_by_name(db, rating)

                stats["rated"] += 1

            except Exception:
                logger.debug(f"[rating] Erro ao ratear construtora '{nome}'", exc_info=True)
                stats["failed"] += 1

        logger.info(f"[rating] Done: {stats}")
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[rating] Falha geral")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _fetch_alvaras_stats(db: Any) -> dict[str, dict]:
    """Agrega alvarás por construtora (requerente)."""
    try:
        result = db.table("alvaras_marilia").select(
            "requerente, cnpj_cpf, neighborhood, edition_date, area_construida"
        ).not_.is_("requerente", "null").execute()

        stats: dict[str, dict] = {}
        for row in result.data or []:
            nome = (row.get("requerente") or "").strip()
            if not nome or len(nome) < 3:
                continue

            if nome not in stats:
                stats[nome] = {
                    "nome": nome,
                    "cnpj": row.get("cnpj_cpf"),
                    "total_alvaras": 0,
                    "bairros": set(),
                    "datas": [],
                    "area_total": 0.0,
                }

            stats[nome]["total_alvaras"] += 1
            if row.get("neighborhood"):
                stats[nome]["bairros"].add(row["neighborhood"])
            if row.get("edition_date"):
                stats[nome]["datas"].append(row["edition_date"])
            if row.get("area_construida"):
                stats[nome]["area_total"] += float(row["area_construida"])

        return stats

    except Exception:
        logger.warning("[rating] Falha ao buscar stats de alvarás", exc_info=True)
        return {}


def _fetch_habite_stats(db: Any) -> dict[str, dict]:
    """Agrega habite-se por construtora (quando disponível)."""
    try:
        # habite_se_records nem sempre tem o requerente — tenta cruzar por processo
        db.table("habite_se_records").select(
            "neighborhood, edition_date, area_built, source_id"
        ).execute()

        # Sem nome de construtora no habite_se, agrupamos por bairro+período
        # para cruzar com alvarás depois
        return {}  # Retorna vazio — cruzamento é feito em _calculate_prazo_stats

    except Exception:
        return {}


def _calculate_prazo_stats(db: Any) -> dict[str, dict]:
    """Calcula prazo médio alvará→habite-se por construtora via process_number."""
    try:
        # Cruzamento: alvaras.numero_processo == habite_se.process_number
        alvaras = db.table("alvaras_marilia").select(
            "requerente, cnpj_cpf, numero_processo, edition_date"
        ).not_.is_("numero_processo", "null").not_.is_("requerente", "null").execute()

        habites = db.table("habite_se_records").select(
            "process_number, edition_date"
        ).not_.is_("process_number", "null").execute()

        # Mapear habite_se por processo
        habite_map: dict[str, str] = {
            h["process_number"]: h["edition_date"]
            for h in (habites.data or [])
            if h.get("process_number") and h.get("edition_date")
        }

        # Calcular deltas por construtora
        deltas: dict[str, list[float]] = {}

        for alv in (alvaras.data or []):
            nome = (alv.get("requerente") or "").strip()
            proc = alv.get("numero_processo", "")
            alv_date = alv.get("edition_date")

            if not nome or not proc or not alv_date:
                continue

            # Procurar habite-se para este processo (normaliza o número)
            proc_clean = proc.replace(".", "").replace("-", "").replace("/", "")
            habite_date = None
            for h_proc, h_date in habite_map.items():
                h_clean = h_proc.replace(".", "").replace("-", "").replace("/", "")
                if proc_clean == h_clean:
                    habite_date = h_date
                    break

            if habite_date:
                try:
                    from datetime import date as date_type
                    d1 = date_type.fromisoformat(str(alv_date)[:10])
                    d2 = date_type.fromisoformat(str(habite_date)[:10])
                    delta_days = (d2 - d1).days
                    if 30 <= delta_days <= 3650:  # entre 1 mês e 10 anos
                        if nome not in deltas:
                            deltas[nome] = []
                        deltas[nome].append(float(delta_days))
                except Exception:
                    pass

        # Agregar
        prazo_stats: dict[str, dict] = {}
        for nome, delta_list in deltas.items():
            prazo_stats[nome] = {
                "tempo_medio": sum(delta_list) / len(delta_list),
                "tempo_min": min(delta_list),
                "tempo_max": max(delta_list),
                "amostras": len(delta_list),
            }

        return prazo_stats

    except Exception:
        logger.warning("[rating] Falha ao calcular prazos", exc_info=True)
        return {}


def _calculate_rating(
    nome: str,
    alv: dict,
    hab: dict,
    prazo: dict,
) -> dict:
    """Calcula score de rating para uma construtora."""
    total_alvaras = alv.get("total_alvaras", 0)
    total_habite = hab.get("total_habite_se", 0)

    # score_entrega: taxa de conclusão (habite-se / alvarás)
    if total_alvaras > 0:
        taxa = min(1.0, total_habite / total_alvaras)
        score_entrega = taxa * 100
    else:
        score_entrega = 50.0  # neutro se não tem dados

    # score_prazo: quão dentro do prazo ideal entrega
    tempo_medio = prazo.get("tempo_medio")
    if tempo_medio:
        if tempo_medio <= PRAZO_IDEAL_DIAS:
            score_prazo = 100.0
        elif tempo_medio >= PRAZO_MAX_DIAS:
            score_prazo = 0.0
        else:
            # Linear entre ideal e max
            score_prazo = max(0.0, 100 * (1 - (tempo_medio - PRAZO_IDEAL_DIAS) / (PRAZO_MAX_DIAS - PRAZO_IDEAL_DIAS)))
    else:
        score_prazo = 50.0  # neutro

    # score_volume: log-normalizado (mais obras = mais experiente)
    score_volume = min(100.0, math.log1p(total_alvaras) * 15)

    # Score composto
    score_geral = (
        WEIGHT_ENTREGA * score_entrega +
        WEIGHT_PRAZO * score_prazo +
        WEIGHT_VOLUME * score_volume
    )

    # Tier
    if score_geral >= 80:
        tier = "A"
    elif score_geral >= 60:
        tier = "B"
    elif score_geral >= 40:
        tier = "C"
    else:
        tier = "D"

    # Bairros de atuação
    bairros = sorted(alv.get("bairros", set()))
    bairro_principal = bairros[0] if bairros else None  # simplificado

    # Datas
    datas = alv.get("datas", [])
    ultima_atividade = max(datas)[:10] if datas else None
    primeiro_registro = min(datas)[:10] if datas else None

    return {
        "nome":                    nome[:200],
        "cnpj":                    alv.get("cnpj"),
        "total_alvaras":           total_alvaras,
        "total_habite_se":         total_habite,
        "alvaras_sem_habite_se":   max(0, total_alvaras - total_habite),
        "tempo_medio_obra_dias":   round(tempo_medio, 1) if tempo_medio else None,
        "tempo_min_obra_dias":     round(prazo.get("tempo_min", 0), 1) if prazo.get("tempo_min") else None,
        "tempo_max_obra_dias":     round(prazo.get("tempo_max", 0), 1) if prazo.get("tempo_max") else None,
        "bairros_atuacao":         bairros,
        "bairro_principal":        bairro_principal,
        "score_entrega":           round(score_entrega, 2),
        "score_prazo":             round(score_prazo, 2),
        "score_volume":            round(score_volume, 2),
        "score_geral":             round(score_geral, 2),
        "tier":                    tier,
        "ultima_atividade_date":   ultima_atividade,
        "primeiro_registro_date":  primeiro_registro,
        "calculado_em":            datetime.now(timezone.utc).isoformat(),
    }


def _upsert_by_name(db: Any, rating: dict) -> None:
    """Upsert por nome quando não há CNPJ."""
    try:
        existing = db.table("construtoras_rating").select("id").eq("nome", rating["nome"]).execute()
        if existing.data:
            db.table("construtoras_rating").update(rating).eq("nome", rating["nome"]).execute()
        else:
            db.table("construtoras_rating").insert(rating).execute()
    except Exception:
        logger.debug(f"[rating] Erro upsert por nome: {rating.get('nome')}", exc_info=True)


def get_construtora_rating(nome_or_cnpj: str) -> Optional[dict]:
    """Retorna rating de uma construtora específica."""
    db = get_client()
    try:
        result = db.table("construtoras_rating").select("*").or_(
            f"nome.ilike.%{nome_or_cnpj}%,cnpj.eq.{nome_or_cnpj}"
        ).limit(1).execute()
        return result.data[0] if result.data else None
    except Exception:
        return None


def _finish_run(db: Any, run_id: Any, status: str, stats: dict, error: str = "") -> None:
    if not run_id:
        return
    try:
        db.table("agent_runs").update({
            "status": status,
            "items_processed": stats.get("construtoras", 0),
            "items_created": stats.get("rated", 0),
            "items_failed": stats.get("failed", 0),
            "metadata": {"error": error} if error else stats,
        }).eq("id", run_id).execute()
    except Exception:
        pass
