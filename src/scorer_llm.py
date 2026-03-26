"""LLM Scorer — second opinion on top opportunities using Gemini."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.db import get_client
from src.llm import score_opportunity, GEMINI_API_KEY

logger = logging.getLogger(__name__)


def run_llm_scorer(limit: int = 20) -> dict[str, int]:
    """Get LLM second opinion on top opportunities."""
    db = get_client()
    stats = {"scored": 0, "improved": 0, "failed": 0}

    if not GEMINI_API_KEY:
        logger.warning("[scorer_llm] No GEMINI_API_KEY, skipping")
        return stats

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "scorer_llm", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        # Get top opportunities with their listing data + enriched features
        result = (
            db.table("opportunities")
            .select(
                "id, listing_id, score, score_breakdown, reason, "
                "listing:listings(id, source, neighborhood, sale_price, "
                "total_area, price_per_m2, features, description, title)"
            )
            .order("score", desc=True)
            .limit(limit)
            .execute()
        )

        for opp in result.data:
            listing = opp.get("listing")
            if isinstance(listing, list):
                listing = listing[0] if listing else None
            if not listing:
                continue

            # Build context from enriched features
            features = listing.get("features") or {}
            if isinstance(features, list):
                features = {}

            listing_data = {
                "sale_price": listing.get("sale_price"),
                "total_area": listing.get("total_area"),
                "neighborhood": listing.get("neighborhood"),
                "infra": features.get("infraestrutura") or [],
                "proximidades": features.get("proximidades") or [],
                "terrain": features.get("caracteristicas_terreno") or [],
                "zoning": features.get("zoneamento"),
            }

            try:
                result_llm = score_opportunity(listing_data, opp["score"])
                if result_llm:
                    nota = result_llm.get("nota", 0)
                    justificativa = result_llm.get("justificativa", "")

                    # Update opportunity with LLM opinion
                    new_breakdown = opp.get("score_breakdown", {})
                    new_breakdown["llm_nota"] = nota
                    new_breakdown["llm_justificativa"] = justificativa

                    # Build enhanced reason
                    new_reason = opp.get("reason", "")
                    if justificativa:
                        new_reason = f"{justificativa} | {new_reason}"

                    db.table("opportunities").update({
                        "score_breakdown": new_breakdown,
                        "reason": new_reason[:500],
                    }).eq("id", opp["id"]).execute()

                    stats["scored"] += 1
                    logger.info(
                        f"[scorer_llm] #{opp['listing_id']} "
                        f"{listing.get('neighborhood', '?')}: "
                        f"LLM nota={nota}/10 — {justificativa[:80]}"
                    )
                else:
                    stats["failed"] += 1

            except Exception:
                stats["failed"] += 1
                logger.debug(f"[scorer_llm] Failed for #{opp['id']}", exc_info=True)

        logger.info(
            f"[scorer_llm] Done: {stats['scored']} scored, {stats['failed']} failed"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[scorer_llm] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))
        raise

    return stats


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
        "items_processed": stats["scored"],
        "items_failed": stats["failed"],
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    db.table("agent_runs").update(update).eq("id", run_id).execute()
