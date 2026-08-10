"""Embedder — gera vetores text-embedding-004 para listings e documentos municipais.

Preenche:
  - listing_embeddings (busca de similares, clustering)
  - document_embeddings (RAG de CMDU atas, alvarás, EIVs, Plano Diretor)

Criado por supabase/migrations/*_pgvector.sql.
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any

from src.db import get_client

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-004"
EMBEDDING_DIM = 768
BATCH_SIZE = 50
SLEEP_BETWEEN_BATCHES = 1.0


def run_embedder(
    listings: bool = True,
    documents: bool = True,
    limit: int = 500,
) -> dict[str, int]:
    """Gera embeddings para listings e/ou documentos municipais."""
    stats = {"listings_embedded": 0, "documents_embedded": 0, "failed": 0}
    db = get_client()

    try:
        _client = _get_embedding_client()
    except Exception:
        logger.exception("[embedder] Não foi possível inicializar cliente Gemini")
        return stats

    if listings:
        stats["listings_embedded"] = _embed_listings(db, _client, limit)

    if documents:
        stats["documents_embedded"] = _embed_documents(db, _client, limit)

    logger.info(
        f"[embedder] Done: listings={stats['listings_embedded']} "
        f"docs={stats['documents_embedded']} failed={stats['failed']}"
    )
    return stats


def _get_embedding_client():
    from google import genai
    import os
    from dotenv import load_dotenv
    load_dotenv()

    vertex_project = os.getenv("VERTEX_PROJECT", "")
    if vertex_project:
        return genai.Client(
            vertexai=True,
            project=vertex_project,
            location=os.getenv("VERTEX_LOCATION", "us-central1"),
        )
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY ou VERTEX_PROJECT obrigatório")
    return genai.Client(api_key=api_key)


def _embed_listings(db: Any, client: Any, limit: int) -> int:
    """Embeds listings sem embedding ou com texto mudado."""
    # Buscar listings sem embedding (ou desatualizados)
    result = (
        db.table("listings")
        .select("id, neighborhood, total_area, property_type, features, sale_price, price_per_m2")
        .eq("is_active", True)
        .not_.is_("neighborhood", "null")
        .limit(limit)
        .execute()
    )
    listings = result.data or []

    # Filtrar os que já têm embedding atualizado
    existing = _get_existing_hashes(db, "listing_embeddings", "listing_id",
                                    [l["id"] for l in listings])

    count = 0
    batch = []
    batch_ids = []

    for listing in listings:
        text = _listing_to_text(listing)
        content_hash = hashlib.sha1(text.encode()).hexdigest()
        lid = listing["id"]

        if existing.get(lid) == content_hash:
            continue  # sem mudança

        batch.append(text)
        batch_ids.append((lid, content_hash))

        if len(batch) >= BATCH_SIZE:
            count += _flush_listing_batch(db, client, batch, batch_ids)
            batch, batch_ids = [], []
            time.sleep(SLEEP_BETWEEN_BATCHES)

    if batch:
        count += _flush_listing_batch(db, client, batch, batch_ids)

    return count


def _flush_listing_batch(
    db: Any, client: Any, texts: list[str], meta: list[tuple[int, str]]
) -> int:
    try:
        embeddings = _batch_embed(client, texts)
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for (lid, content_hash), emb in zip(meta, embeddings):
            if emb is None:
                continue
            rows.append({
                "listing_id": lid,
                "embedding": emb,
                "content_hash": content_hash,
                "model": EMBEDDING_MODEL,
                "embedded_at": now,
            })
        if rows:
            db.table("listing_embeddings").upsert(rows, on_conflict="listing_id").execute()
        return len(rows)
    except Exception:
        logger.exception("[embedder] flush listing batch falhou")
        return 0


def _embed_documents(db: Any, client: Any, limit: int) -> int:
    """Embeds document_embeddings rows onde embedding IS NULL."""
    result = (
        db.table("document_embeddings")
        .select("id, source_table, source_id, chunk_index, chunk_text, content_hash")
        .is_("embedding", "null")
        .limit(limit)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return 0

    count = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i: i + BATCH_SIZE]
        texts = [r["chunk_text"] for r in batch]
        try:
            embeddings = _batch_embed(client, texts)
            now = datetime.now(timezone.utc).isoformat()
            for row, emb in zip(batch, embeddings):
                if emb is None:
                    continue
                db.table("document_embeddings").update({
                    "embedding": emb,
                    "embedded_at": now,
                }).eq("id", row["id"]).execute()
                count += 1
            time.sleep(SLEEP_BETWEEN_BATCHES)
        except Exception:
            logger.exception(f"[embedder] document batch {i} falhou")

    return count


def _batch_embed(client: Any, texts: list[str]) -> list[list[float] | None]:
    """Chama text-embedding-004 para um batch de textos. Retorna lista de vetores."""
    from google.genai import types
    results: list[list[float] | None] = []
    for text in texts:
        try:
            resp = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=text,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
            )
            values = resp.embeddings[0].values if resp.embeddings else None
            results.append(list(values) if values else None)
        except Exception:
            logger.warning("[embedder] embed_content falhou para chunk")
            results.append(None)
    return results


def _listing_to_text(listing: dict) -> str:
    """Converte listing em texto para embedding."""
    import json
    parts = []
    parts.append(f"Bairro: {listing.get('neighborhood', '')}")
    parts.append(f"Tipo: {listing.get('property_type', '')}")
    area = listing.get("total_area")
    if area:
        parts.append(f"Área: {area}m²")
    price = listing.get("sale_price")
    if price:
        parts.append(f"Preço: R${price:,.0f}")
    pm2 = listing.get("price_per_m2")
    if pm2:
        parts.append(f"R$/m²: {pm2:.0f}")
    feat = listing.get("features") or {}
    if isinstance(feat, str):
        try:
            feat = json.loads(feat)
        except Exception:
            feat = {}
    infra = feat.get("infraestrutura") or []
    if infra:
        parts.append(f"Infraestrutura: {', '.join(infra[:5])}")
    prox = feat.get("proximidades") or []
    if prox:
        parts.append(f"Próximo: {', '.join(prox[:5])}")
    return " | ".join(parts)


def _get_existing_hashes(
    db: Any, table: str, id_col: str, ids: list[int]
) -> dict[int, str]:
    if not ids:
        return {}
    try:
        result = (
            db.table(table)
            .select(f"{id_col}, content_hash")
            .in_(id_col, ids)
            .execute()
        )
        return {r[id_col]: r.get("content_hash", "") for r in (result.data or [])}
    except Exception:
        return {}


def search_similar_listings(
    db: Any, listing_id: int, top_k: int = 5
) -> list[dict[str, Any]]:
    """Retorna listings similares via pgvector (wrapper para RPC find_similar_listings)."""
    try:
        result = db.rpc("find_similar_listings", {
            "p_listing_id": listing_id,
            "match_count": top_k,
            "similarity_threshold": 0.75,
        }).execute()
        return result.data or []
    except Exception:
        logger.warning(f"[embedder] find_similar_listings falhou para {listing_id}")
        return []


def search_documents(
    db: Any,
    query_text: str,
    source_filter: str | None = None,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Busca semântica em document_embeddings (CMDU, alvarás, EIVs, Plano Diretor)."""
    try:
        client = _get_embedding_client()
        from google.genai import types
        resp = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=query_text,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
        )
        if not resp.embeddings:
            return []
        query_vec = list(resp.embeddings[0].values)
        result = db.rpc("search_documents", {
            "query_embedding": query_vec,
            "source_filter": source_filter,
            "match_count": top_k,
            "similarity_threshold": 0.65,
        }).execute()
        return result.data or []
    except Exception:
        logger.exception("[embedder] search_documents falhou")
        return []
