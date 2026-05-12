"""Regulatory Scorer — Track C.

Emite SINAIS (regulatory_signals) para listings com risco regulatório:
- zoning_mismatch  — uso pretendido vs. zona do plano diretor (Gemini text analysis)
- distance_water   — coord dentro da faixa de APP de cursos d'água (Lei 12.651/2012)
- seller_litigation — vendedor (features.cnpj_vendedor) com histórico em DataJud

Política: NUNCA bloqueia listing. Apenas insere signal. Decisão é humana.

Falhas externas → log warning + skip (não levanta).
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from src.collectors.seller_litigation import _normalize_doc
from src.db import get_client
from src.llm import GEMINI_API_KEY, _generate, _parse_json
from src.regulatory_geo import nearest_water_course

logger = logging.getLogger(__name__)


# --- helpers ----------------------------------------------------------------

def _signal_payload(
    listing: dict[str, Any],
    signal_type: str,
    severity: str,
    title: str,
    description: str,
    source: str,
    raw: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return {
        "listing_id": listing.get("id"),
        "neighborhood": listing.get("neighborhood"),
        "signal_type": signal_type,
        "severity": severity,
        "title": title[:200],
        "description": (description or "")[:1500],
        "source": source,
        "raw": raw or {},
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }


def _existing_signal_types(db: Any, listing_id: int) -> set[str]:
    try:
        result = (
            db.table("regulatory_signals")
            .select("signal_type")
            .eq("listing_id", listing_id)
            .execute()
        )
        return {r["signal_type"] for r in (result.data or [])}
    except Exception:
        return set()


def _load_zones(db: Any) -> list[dict[str, Any]]:
    try:
        result = db.table("zoning_zones").select("*").execute()
        return result.data or []
    except Exception:
        logger.warning("[regulatory] zoning_zones load failed", exc_info=True)
        return []


# --- checks -----------------------------------------------------------------

def check_zoning(
    listing: dict[str, Any], zones: list[dict[str, Any]]
) -> Optional[dict[str, Any]]:
    """Cruza uso pretendido (extraído da descrição via Gemini) com zoning_zones."""
    if not GEMINI_API_KEY or not zones:
        return None

    description = (listing.get("description") or "")[:1200]
    title = (listing.get("title") or "")[:200]
    features = listing.get("features") or {}
    if isinstance(features, list):
        features = {}

    zoning_mentioned = features.get("zoneamento_mencionado") or features.get("zoneamento")

    prompt = f"""Analise este anúncio de terreno em Marília-SP e identifique o USO PRETENDIDO pelo vendedor/anunciante.

Título: {title}
Descrição: {description}
Zoneamento mencionado no anúncio (se houver): {zoning_mentioned or "não informado"}

Retorne APENAS JSON:
{{
  "uso_pretendido": "residencial" | "comercial" | "misto" | "industrial" | "indefinido",
  "confianca": 0-1,
  "trechos_relevantes": ["frases curtas que indicam o uso"]
}}"""

    text = _generate(prompt, max_tokens=300)
    parsed = _parse_json(text)
    if not parsed:
        return None
    uso = (parsed.get("uso_pretendido") or "").lower()
    if uso in ("indefinido", ""):
        return None
    conf = float(parsed.get("confianca") or 0)
    if conf < 0.5:
        return None

    # Heurística: se descrição menciona código de zona explícito, casa com zones
    text_full = f"{title} {description}".upper()
    matched_zone: Optional[dict[str, Any]] = None
    for z in zones:
        code = (z.get("zone_code") or "").upper()
        if code and re.search(rf"\b{re.escape(code)}\b", text_full):
            matched_zone = z
            break

    if not matched_zone:
        # Sem zona explícita, não podemos afirmar mismatch.
        return None

    allowed = [u.lower() for u in (matched_zone.get("allowed_uses") or [])]
    if uso in allowed or "misto" in allowed:
        return None

    return _signal_payload(
        listing,
        signal_type="zoning_mismatch",
        severity="critical",
        title=f"Uso {uso} incompatível com zona {matched_zone.get('zone_code')}",
        description=(
            f"Vendedor anuncia uso '{uso}', mas zona "
            f"{matched_zone.get('zone_code')} ({matched_zone.get('zone_name')}) "
            f"permite apenas: {', '.join(allowed) or '—'}. "
            f"Trechos: {parsed.get('trechos_relevantes')}"
        ),
        source="gemini+zoning_zones",
        raw={
            "uso_pretendido": uso,
            "confianca": conf,
            "zone": matched_zone.get("zone_code"),
            "allowed_uses": allowed,
        },
    )


def check_app(listing: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Distância p/ rios/córregos hardcoded. < 30m = warning (APP)."""
    lat = listing.get("latitude")
    lng = listing.get("longitude")
    if lat is None or lng is None:
        return None

    near = nearest_water_course(float(lat), float(lng))
    if not near or not near.get("within_app"):
        return None

    dist = near["distance_m"]
    buffer_m = near["app_buffer_m"]

    return _signal_payload(
        listing,
        signal_type="app_overlap" if dist < buffer_m / 2 else "distance_water",
        severity="warning",
        title=f"Terreno a {dist:.0f}m de {near['nome']} (APP {buffer_m}m)",
        description=(
            f"Coordenadas indicam proximidade com {near['nome']} ({near['tipo']}). "
            f"Lei 12.651/2012 exige faixa marginal de {buffer_m}m. "
            f"Verificar sobreposição com APP antes de qualquer projeto."
        ),
        source="regulatory_geo.hardcoded",
        raw=near,
    )


def check_seller_history(
    listing: dict[str, Any]
) -> Optional[dict[str, Any]]:
    """Hash de features.cnpj_vendedor → consulta seller_history."""
    features = listing.get("features") or {}
    if isinstance(features, list):
        features = {}

    doc = (
        features.get("cnpj_vendedor")
        or features.get("cpf_vendedor")
        or features.get("doc_vendedor")
    )
    if not doc:
        return None
    digits = _normalize_doc(str(doc))
    if not digits:
        return None

    doc_hash = hashlib.sha256(digits.encode("utf-8")).hexdigest()

    db = get_client()
    try:
        result = (
            db.table("seller_history")
            .select("*")
            .eq("doc_hash", doc_hash)
            .limit(1)
            .execute()
        )
        row = (result.data or [None])[0]
    except Exception:
        logger.warning("[regulatory] seller_history lookup failed", exc_info=True)
        return None

    if not row or (row.get("litigation_count") or 0) <= 0:
        return None

    count = row["litigation_count"]
    last = row.get("last_litigation_at")
    severity = "critical" if count >= 5 else "warning"

    return _signal_payload(
        listing,
        signal_type="seller_litigation",
        severity=severity,
        title=f"Vendedor com {count} processo(s) registrado(s)",
        description=(
            f"Histórico DataJud indica {count} processo(s) envolvendo o vendedor "
            f"(último: {last or 'desconhecido'}). Avaliar risco de litígio na compra."
        ),
        source="seller_history.datajud",
        raw={
            "doc_hash_prefix": doc_hash[:8],
            "litigation_count": count,
            "last_litigation_at": last,
        },
    )


# --- orchestrator -----------------------------------------------------------

def _load_listing(db: Any, listing_id: int) -> Optional[dict[str, Any]]:
    try:
        result = (
            db.table("listings")
            .select(
                "id, title, description, neighborhood, latitude, longitude, features"
            )
            .eq("id", listing_id)
            .limit(1)
            .execute()
        )
        return (result.data or [None])[0]
    except Exception:
        logger.warning(f"[regulatory] load listing #{listing_id} failed", exc_info=True)
        return None


def assess_listing(listing_id: int) -> list[dict[str, Any]]:
    """Avalia 1 listing nas 3 dimensões; insere signals novos.

    Returns: lista dos signals criados (já com id).
    """
    db = get_client()
    listing = _load_listing(db, listing_id)
    if not listing:
        return []

    zones = _load_zones(db)
    existing = _existing_signal_types(db, listing_id)
    to_insert: list[dict[str, Any]] = []

    # zoning
    if "zoning_mismatch" not in existing:
        try:
            sig = check_zoning(listing, zones)
            if sig:
                to_insert.append(sig)
        except Exception:
            logger.warning(f"[regulatory] zoning check failed #{listing_id}", exc_info=True)

    # app / distance_water
    if not {"app_overlap", "distance_water"} & existing:
        try:
            sig = check_app(listing)
            if sig:
                to_insert.append(sig)
        except Exception:
            logger.warning(f"[regulatory] app check failed #{listing_id}", exc_info=True)

    # seller history
    if "seller_litigation" not in existing:
        try:
            sig = check_seller_history(listing)
            if sig:
                to_insert.append(sig)
        except Exception:
            logger.warning(
                f"[regulatory] seller check failed #{listing_id}", exc_info=True
            )

    if not to_insert:
        return []

    try:
        result = db.table("regulatory_signals").insert(to_insert).execute()
        return result.data or []
    except Exception:
        logger.warning(
            f"[regulatory] batch insert failed for #{listing_id}", exc_info=True
        )
        return []


def run_regulatory_scorer(limit: int = 100) -> dict[str, int]:
    """Itera top opportunities (score >= 50) e avalia regulatório.

    Registra execução em agent_runs. Nunca bloqueia listings.
    """
    db = get_client()
    stats = {"processed": 0, "signals_created": 0, "critical": 0, "failed": 0}

    run_id: Optional[int] = None
    try:
        run_result = (
            db.table("agent_runs")
            .insert({"agent_name": "regulatory_scorer", "status": "running"})
            .execute()
        )
        run_id = run_result.data[0]["id"] if run_result.data else None
    except Exception:
        logger.warning("[regulatory] agent_runs insert failed", exc_info=True)

    try:
        opps = (
            db.table("opportunities")
            .select("id, listing_id, score")
            .gte("score", 50)
            .order("score", desc=True)
            .limit(limit)
            .execute()
        )

        for opp in (opps.data or []):
            listing_id = opp.get("listing_id")
            if not listing_id:
                continue
            stats["processed"] += 1
            try:
                created = assess_listing(int(listing_id))
                stats["signals_created"] += len(created)
                stats["critical"] += sum(
                    1 for s in created if s.get("severity") == "critical"
                )
                if created:
                    logger.info(
                        f"[regulatory] #{listing_id}: {len(created)} signals "
                        f"({[s.get('signal_type') for s in created]})"
                    )
            except Exception:
                stats["failed"] += 1
                logger.warning(
                    f"[regulatory] assess_listing #{listing_id} failed", exc_info=True
                )

        _finish_run(db, run_id, "completed", stats)
        logger.info(f"[regulatory] Done: {stats}")
    except Exception as e:
        logger.exception("[regulatory] Failed")
        _finish_run(db, run_id, "failed", stats, str(e))
        # Política: não levantar — mantém pipeline rodando.

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
        "items_processed": stats.get("processed", 0),
        "metadata": stats,
    }
    if error:
        update["error_message"] = error[:1000]
    try:
        db.table("agent_runs").update(update).eq("id", run_id).execute()
    except Exception:
        logger.warning("[regulatory] agent_runs update failed", exc_info=True)
