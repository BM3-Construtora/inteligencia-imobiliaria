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
    """Normalize all unique neighborhood names using Claude Haiku."""
    result = db.table("neighborhoods").select("name").execute()
    names = [r["name"] for r in result.data if r["name"]]

    if not names:
        return

    logger.info(f"[llm_enricher] Normalizing {len(names)} neighborhood names")

    # Process in batches of 50
    for i in range(0, len(names), 50):
        batch = names[i:i+50]
        mapping = batch_normalize_neighborhoods(batch)

        for original, normalized in mapping.items():
            if original != normalized and normalized:
                # Update listings
                db.table("listings").update({
                    "neighborhood": normalized,
                }).eq("neighborhood", original).execute()

                # Update neighborhoods table
                db.table("neighborhoods").update({
                    "name": normalized,
                }).eq("name", original).execute()

                stats["neighborhoods_normalized"] += 1
                logger.info(f"[llm_enricher] Neighborhood: '{original}' → '{normalized}'")


def _extract_attributes(db: Any, stats: dict[str, int]) -> None:
    """Extract structured attributes from land listing descriptions."""
    # Get land listings with description but no extracted features yet
    result = (
        db.table("listings")
        .select("id, title, description, features, neighborhood")
        .eq("is_active", True)
        .eq("property_type", "land")
        .not_.is_("description", "null")
        .limit(100)  # Limit to control API costs
        .execute()
    )

    listings = result.data
    # Filter to only those without enriched features
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
