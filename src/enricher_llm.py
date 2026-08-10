"""LLM Enricher — uses Claude Haiku to enrich listing data post-normalization."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from postgrest.exceptions import APIError

from src.db import get_client
from src.llm import extract_listing_attributes, batch_normalize_neighborhoods
from src.llm import _generate, _parse_json  # type: ignore

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

                try:
                    db.table("neighborhoods").update({
                        "name": normalized,
                    }).eq("name", original).execute()
                except APIError as e:
                    # O nome canônico já existe como outra linha: renomear
                    # violaria a unique (name, city). Os listings já apontam
                    # pro normalizado, então basta remover a linha duplicada.
                    if e.code == "23505" or "duplicate key" in str(e):
                        db.table("neighborhoods").delete().eq("name", original).execute()
                    else:
                        raise

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


def run_canonicalize_neighborhoods() -> dict[str, int]:
    """One-shot backfill: cluster existing neighborhood names into canonical form via LLM."""
    db = get_client()
    stats = {"original_count": 0, "canonical_count": 0, "merged_count": 0, "deleted": 0}

    run_result = (
        db.table("agent_runs")
        .insert({"agent_name": "canon_bairros", "status": "running"})
        .execute()
    )
    run_id = run_result.data[0]["id"] if run_result.data else None

    try:
        # 1) Pega lista distinta de bairros via listings (paginado p/ furar limite 1000)
        names: set[str] = set()
        page_size = 1000
        offset = 0
        while True:
            res = (
                db.table("listings")
                .select("neighborhood")
                .not_.is_("neighborhood", "null")
                .range(offset, offset + page_size - 1)
                .execute()
            )
            rows = res.data or []
            if not rows:
                break
            for r in rows:
                n = (r.get("neighborhood") or "").strip()
                if n:
                    names.add(n)
            if len(rows) < page_size:
                break
            offset += page_size

        original = sorted(names)
        stats["original_count"] = len(original)
        logger.info(f"[canon] Fetched {len(original)} distinct neighborhood names")

        if not original:
            _finish_run(db, run_id, "completed", {"processed": 0, "enriched": 0, **stats})
            return stats

        # 2) Agrupa por token inicial (case-insensitive, sem pontuação)
        groups: dict[str, list[str]] = {}
        for name in original:
            token = name.split()[0].strip(".,").lower() if name.split() else "_"
            # Normaliza abreviações comuns p/ chave de agrupamento
            token = {
                "jd": "jardim", "jd.": "jardim",
                "pq": "parque", "pq.": "parque",
                "res": "residencial", "res.": "residencial",
                "vl": "vila", "vl.": "vila",
                "n.h.": "nh", "nh": "nh",
            }.get(token, token)
            groups.setdefault(token, []).append(name)

        logger.info(f"[canon] Grouped into {len(groups)} clusters by initial token")

        # 3) Para cada grupo, chama LLM (chunks de 60 p/ não estourar contexto)
        full_map: dict[str, str] = {}
        for token, group_names in groups.items():
            for i in range(0, len(group_names), 60):
                chunk = group_names[i:i + 60]
                mapping = _canon_llm_call(chunk)
                if mapping:
                    full_map.update(mapping)

        # 4) UPDATE listings em batch por canônico
        # Agrupa: canônico → [originais]
        canon_to_originals: dict[str, list[str]] = {}
        for orig, canon in full_map.items():
            if not canon or not isinstance(canon, str):
                continue
            canon_clean = canon.strip()
            if not canon_clean:
                continue
            canon_to_originals.setdefault(canon_clean, []).append(orig)

        merged = 0
        canonical_names: set[str] = set(canon_to_originals.keys())
        for canon, origs in canon_to_originals.items():
            to_change = [o for o in origs if o != canon]
            if not to_change:
                continue
            try:
                db.table("listings").update(
                    {"neighborhood": canon}
                ).in_("neighborhood", to_change).execute()
                merged += len(to_change)
                logger.info(f"[canon] {len(to_change)} → '{canon}'")
            except Exception:
                logger.warning(f"[canon] update failed for canon='{canon}'", exc_info=True)

        stats["canonical_count"] = len(canonical_names)
        stats["merged_count"] = merged

        # 5) DELETE neighborhoods órfãos com total_listings < 5 (apenas dups pequenos)
        try:
            res = (
                db.table("neighborhoods")
                .select("name, total_listings")
                .execute()
            )
            orphans = [
                r["name"] for r in (res.data or [])
                if r.get("name") not in canonical_names
                and (r.get("total_listings") or 0) < 5
            ]
            if orphans:
                # Delete em batches de 100
                for i in range(0, len(orphans), 100):
                    batch = orphans[i:i + 100]
                    db.table("neighborhoods").delete().in_("name", batch).execute()
                stats["deleted"] = len(orphans)
                logger.info(f"[canon] Deleted {len(orphans)} orphan neighborhoods (total_listings<5)")
        except Exception:
            logger.warning("[canon] orphan cleanup failed", exc_info=True)

        logger.info(
            f"[canon] {stats['original_count']} → {stats['canonical_count']} bairros, "
            f"{stats['merged_count']} merged"
        )
        _finish_run(db, run_id, "completed", {"processed": stats["original_count"], "enriched": merged, **stats})

    except Exception as e:
        logger.exception("[canon] Failed")
        _finish_run(db, run_id, "failed", {"processed": 0, "enriched": 0, **stats}, str(e))
        raise

    return stats


def _canon_llm_call(names: list[str]) -> dict[str, str]:
    """LLM cluster call for a group of names."""
    if not names:
        return {}
    names_list = "\n".join(f"- {n}" for n in names)
    prompt = (
        f"Aqui estão {len(names)} nomes de bairros de Marília-SP. "
        f"Agrupe os duplicados/variações e retorne um mapa nome_original → nome_canônico.\n\n"
        f"Critério: mesma localização física. Corrija abreviações "
        f"(Jd→Jardim, Pq→Parque, Res→Residencial, Vl→Vila, N.H.→Núcleo Habitacional), "
        f"erros de digitação e casing. Use o nome oficial completo.\n\n"
        f"Exemplo: 'Jardim S Antonieta' e 'Jd Santa Antonieta' → 'Jardim Santa Antonieta'.\n\n"
        f"Se um nome não tem duplicata, mantenha-o (apenas corrija a forma).\n"
        f"Retorne APENAS JSON: {{\"original\": \"canônico\", ...}}\n\n"
        f"Nomes:\n{names_list}"
    )
    text = _generate(prompt, max_tokens=8000)
    if not text:
        return {}
    result = _parse_json(text)
    return result if isinstance(result, dict) else {}


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
