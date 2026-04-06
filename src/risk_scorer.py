"""Risk Scorer — assesses zoning, environmental, infrastructure and legal risks."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.db import get_client
from src.llm import assess_risk, GEMINI_API_KEY

logger = logging.getLogger(__name__)


def run_risk_scorer(limit: int = 30) -> dict[str, int]:
    """Assess risks for top opportunities using Gemini."""
    db = get_client()
    stats = {"assessed": 0, "high_risk": 0, "failed": 0}

    if not GEMINI_API_KEY:
        logger.warning("[risk] No GEMINI_API_KEY, skipping")
        return stats

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "risk_scorer", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        # Get opportunities that don't have risk assessment yet
        result = (
            db.table("opportunities")
            .select(
                "id, listing_id, score, score_breakdown, "
                "listing:listings(neighborhood, latitude, longitude, features)"
            )
            .gte("score", 50)
            .order("score", desc=True)
            .limit(limit)
            .execute()
        )

        for opp in result.data:
            # Skip if already assessed
            bd = opp.get("score_breakdown", {})
            if bd.get("risk_assessment"):
                continue

            listing = opp.get("listing")
            if isinstance(listing, list):
                listing = listing[0] if listing else None
            if not listing:
                continue

            features = listing.get("features") or {}
            if isinstance(features, list):
                features = {}

            listing_data = {
                "neighborhood": listing.get("neighborhood"),
                "latitude": listing.get("latitude"),
                "longitude": listing.get("longitude"),
                "infra": features.get("infraestrutura") or [],
                "terrain": features.get("caracteristicas_terreno") or [],
                "zoning": features.get("zoneamento"),
            }

            try:
                risk = assess_risk(listing_data)
                if risk:
                    # Store risk in score_breakdown
                    new_bd = {**bd, "risk_assessment": risk}

                    # Check for high risk (any dimension >= 4)
                    max_risk = max(
                        risk.get("risco_zoneamento", 0),
                        risk.get("risco_ambiental", 0),
                        risk.get("risco_infraestrutura", 0),
                        risk.get("risco_legal", 0),
                        risk.get("risco_mercado", 0),
                    )
                    if max_risk >= 4:
                        stats["high_risk"] += 1

                    # Penalizar score baseado no risco máximo:
                    # risco 3 = -5pts, risco 4 = -15pts, risco 5 = -25pts
                    original_score = opp.get("score", 0)
                    penalty = 0
                    if max_risk >= 5:
                        penalty = 25
                    elif max_risk >= 4:
                        penalty = 15
                    elif max_risk >= 3:
                        penalty = 5
                    adjusted_score = max(0, round(original_score - penalty, 1))

                    update_data: dict[str, Any] = {"score_breakdown": new_bd}
                    if penalty > 0:
                        update_data["score"] = adjusted_score
                        new_bd["risk_penalty"] = penalty
                        logger.info(
                            f"[risk] #{opp['listing_id']}: "
                            f"score {original_score} → {adjusted_score} "
                            f"(risk penalty -{penalty})"
                        )

                    db.table("opportunities").update(
                        update_data
                    ).eq("id", opp["id"]).execute()

                    stats["assessed"] += 1
                    resumo = risk.get("resumo", "")
                    logger.info(
                        f"[risk] #{opp['listing_id']} "
                        f"{listing.get('neighborhood', '?')}: "
                        f"max_risk={max_risk} — {resumo[:80]}"
                    )
                else:
                    stats["failed"] += 1

            except Exception:
                stats["failed"] += 1
                logger.debug(f"[risk] Failed for #{opp['id']}", exc_info=True)

        logger.info(
            f"[risk] Done: {stats['assessed']} assessed, "
            f"{stats['high_risk']} high risk, {stats['failed']} failed"
        )
        _finish_run(db, run_id, "completed", stats)

    except Exception as e:
        logger.exception("[risk] Failed")
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
        "items_processed": stats["assessed"],
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    db.table("agent_runs").update(update).eq("id", run_id).execute()
