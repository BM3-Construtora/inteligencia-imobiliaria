"""LLM Enricher — uses Claude Haiku to enrich listing data post-normalization."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.db import get_client
from src.llm import extract_listing_attributes, batch_normalize_neighborhoods

logger = logging.getLogger(__name__)

BATCH_SIZE = 50


def run_llm_enricher() -> dict[str, int]:
    """Enrich listings with Claude Haiku: extract attributes + normalize neighborhoods."""
    db = get_client()
    stats = {"processed": 0, "enriched": 0, "neighborhoods_normalized": 0, "failed": 0}

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "llm_enricher", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        # Phase 1: Normalize neighborhood names in batch
        logger.info("[llm_enricher] Phase 1: Normalizing neighborhood names")
        _normalize_neighborhoods(db, stats)

        # Phase 2: Extract attributes from descriptions (land only, most valuable)
        logger.info("[llm_enricher] Phase 2: Extracting attributes from descriptions")
        _extract_attributes(db, stats)

        logger.info(
            f"[llm_enricher] Done: {stats['processed']} processed, "
            f"{stats['enriched']} enriched, "
            f"{stats['neighborhoods_normalized']} neighborhoods normalized"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[llm_enricher] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


def _normalize_neighborhoods(db: Any, stats: dict[str, int]) -> None:
    """Normalize neighborhood names using Gemini — only ones not yet normalized."""
    # Skip rows already normalized (migration 017 adds normalized_at)
    try:
        result = (
            db.table("neighborhoods")
            .select("name")
            .is_("normalized_at", "null")
            .execute()
        )
    except Exception:
        # Coluna ainda não existe — fallback pro comportamento antigo
        logger.warning("[llm_enricher] normalized_at column missing — run migration 017")
        result = db.table("neighborhoods").select("name").execute()

    names = [r["name"] for r in result.data if r["name"]]

    if not names:
        logger.info("[llm_enricher] All neighborhoods already normalized — skip")
        return

    logger.info(f"[llm_enricher] Normalizing {len(names)} pending neighborhood names")

    now_iso = datetime.now(timezone.utc).isoformat()

    for i in range(0, len(names), 50):
        batch = names[i:i+50]
        mapping = batch_normalize_neighborhoods(batch)

        if not mapping:
            continue

        for original, normalized in mapping.items():
            if original != normalized and normalized:
                db.table("listings").update({
                    "neighborhood": normalized,
                }).eq("neighborhood", original).execute()

                db.table("neighborhoods").update({
                    "name": normalized,
                }).eq("name", original).execute()

                stats["neighborhoods_normalized"] += 1
                logger.info(f"[llm_enricher] Neighborhood: '{original}' → '{normalized}'")

        # Marca todos do batch como já processados (mesmo os que não mudaram)
        try:
            final_names = [mapping.get(n, n) for n in batch]
            db.table("neighborhoods").update(
                {"normalized_at": now_iso}
            ).in_("name", final_names).execute()
        except Exception:
            logger.debug("[llm_enricher] Could not mark normalized_at", exc_info=True)


def _extract_attributes(db: Any, stats: dict[str, int]) -> None:
    """Extract structured attributes from land listing descriptions."""
    # Busca só land com features ainda não enriquecidos (features null OR sem _source)
    # PostgREST: `features->>_source` igual ou diferente de 'claude_haiku'
    try:
        result = (
            db.table("listings")
            .select("id, title, description, features, neighborhood")
            .eq("is_active", True)
            .eq("property_type", "land")
            .not_.is_("description", "null")
            .or_("features.is.null,features->>_source.neq.claude_haiku")
            .limit(100)
            .execute()
        )
    except Exception:
        logger.warning("[llm_enricher] Server-side feature filter failed — fallback")
        result = (
            db.table("listings")
            .select("id, title, description, features, neighborhood")
            .eq("is_active", True)
            .eq("property_type", "land")
            .not_.is_("description", "null")
            .limit(100)
            .execute()
        )

    listings = result.data
    # Segurança: filtra novamente client-side (idempotente)
    to_enrich = [
        l for l in listings
        if not _has_enriched_features(l.get("features"))
    ]

    logger.info(f"[llm_enricher] Enriching {len(to_enrich)} land listings with Haiku")

    for listing in to_enrich:
        stats["processed"] += 1
        try:
            attrs = extract_listing_attributes(
                listing.get("description", ""),
                listing.get("title", ""),
            )

            if attrs:
                # Merge extracted attributes into features
                current_features = listing.get("features") or []
                if isinstance(current_features, str):
                    current_features = []

                enriched_features = {
                    "_source": "claude_haiku",
                    "_enriched_at": datetime.now(timezone.utc).isoformat(),
                    "infraestrutura": attrs.get("infraestrutura", []),
                    "proximidades": attrs.get("proximidades", []),
                    "caracteristicas_terreno": attrs.get("caracteristicas_terreno", []),
                    "zoneamento": attrs.get("zoneamento_mencionado"),
                    "permite_construcao": attrs.get("permite_construcao"),
                    "tem_agua": attrs.get("tem_agua"),
                    "tem_luz": attrs.get("tem_luz"),
                    "eh_condominio": attrs.get("eh_condominio"),
                    "observacoes": attrs.get("observacoes"),
                }

                # Update listing
                update: dict[str, Any] = {
                    "features": enriched_features,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }

                # Normalize neighborhood if Haiku suggested one
                haiku_neigh = attrs.get("bairro_normalizado")
                if haiku_neigh and haiku_neigh != listing.get("neighborhood"):
                    update["neighborhood"] = haiku_neigh

                db.table("listings").update(update).eq("id", listing["id"]).execute()
                stats["enriched"] += 1

        except Exception:
            stats["failed"] += 1
            logger.debug(f"[llm_enricher] Failed for #{listing['id']}", exc_info=True)

        if stats["processed"] % 10 == 0:
            logger.info(
                f"[llm_enricher] Progress: {stats['processed']}/{len(to_enrich)}"
            )


def _has_enriched_features(features: Any) -> bool:
    """Check if features already contain LLM enrichment."""
    if isinstance(features, dict) and features.get("_source") == "claude_haiku":
        return True
    return False


def _finish_run(
    db: Any,
    run_id: Optional[int],
    status: str,
    stats: dict[str, int],
    error: Optional[str] = None,
) -> None:
    if not run_id:
        return
    update = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "items_processed": stats["processed"],
        "items_created": stats["enriched"],
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    db.table("agent_runs").update(update).eq("id", run_id).execute()
