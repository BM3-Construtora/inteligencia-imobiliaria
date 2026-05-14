"""Data Audit Log — registra fluxo de dados para compliance LGPD.

Uso:
    from src.audit import log_data_flow

    log_data_flow(
        pipeline_step="collect",
        agent_name="vivareal",
        data_type="listing",
        source_system="vivareal",
        records_count=47,
        legal_basis="legitimo_interesse",
        external_transfer=False,
    )

Não bloqueia o pipeline — falhas no audit log são silenciosas (logged, não raised).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timezone, date, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Cache de políticas de retenção (carregado na primeira chamada)
_retention_cache: dict[str, int] = {}
_cache_loaded = False
_cache_lock = threading.Lock()

# Mapeamento padrão para fontes não cadastradas
DEFAULT_RETENTION_DAYS: dict[str, int] = {
    "dado_publico": -1,          # indefinido
    "contrato": 730,              # 2 anos
    "legitimo_interesse": 730,    # 2 anos
    "consentimento": 365,         # 1 ano
}


def log_data_flow(
    pipeline_step: str,
    data_type: str,
    source_system: str,
    records_count: int = 0,
    agent_name: Optional[str] = None,
    legal_basis: Optional[str] = None,
    external_transfer: bool = False,
    transfer_safeguard: Optional[str] = None,
    contains_pii: bool = False,
    run_id: Optional[int] = None,
    metadata: Optional[dict] = None,
    data_sample: Optional[Any] = None,  # para gerar hash — não armazena o dado
) -> None:
    """Registra evento de fluxo de dados no audit log. Non-blocking."""
    # Roda em thread separada para não bloquear o pipeline
    thread = threading.Thread(
        target=_write_audit_log,
        args=(
            pipeline_step, data_type, source_system, records_count,
            agent_name, legal_basis, external_transfer, transfer_safeguard,
            contains_pii, run_id, metadata, data_sample,
        ),
        daemon=True,
    )
    thread.start()


def _write_audit_log(
    pipeline_step: str,
    data_type: str,
    source_system: str,
    records_count: int,
    agent_name: Optional[str],
    legal_basis: Optional[str],
    external_transfer: bool,
    transfer_safeguard: Optional[str],
    contains_pii: bool,
    run_id: Optional[int],
    metadata: Optional[dict],
    data_sample: Optional[Any],
) -> None:
    """Escreve no audit log (roda em background thread)."""
    try:
        from src.db import get_client

        db = get_client()

        # Auto-detectar base legal e salvaguarda se não informados
        if legal_basis is None:
            legal_basis = _infer_legal_basis(source_system)

        if external_transfer and transfer_safeguard is None:
            transfer_safeguard = _infer_transfer_safeguard(source_system)

        # Calcular data de expiração
        retention_until = _calculate_retention(source_system, legal_basis)

        # Hash do dado (para rastreabilidade sem armazenar PII)
        data_hash = None
        if data_sample is not None:
            try:
                sample_str = json.dumps(data_sample, default=str, sort_keys=True)
                data_hash = hashlib.sha256(sample_str.encode()).hexdigest()[:16]
            except Exception:
                pass

        db.table("data_audit_log").insert({
            "pipeline_step":     pipeline_step,
            "agent_name":        agent_name,
            "data_type":         data_type,
            "source_system":     source_system,
            "records_count":     records_count,
            "legal_basis":       legal_basis,
            "external_transfer": external_transfer,
            "transfer_safeguard": transfer_safeguard,
            "contains_pii":      contains_pii,
            "data_hash":         data_hash,
            "retention_until":   retention_until.isoformat() if retention_until else None,
            "run_id":            run_id,
            "metadata":          metadata or {},
        }).execute()

    except Exception:
        # Audit log nunca deve quebrar o pipeline
        logger.debug("[audit] Falha ao registrar audit log", exc_info=True)


def _infer_legal_basis(source_system: str) -> str:
    """Infere base legal LGPD pela fonte de dados."""
    PUBLIC_SOURCES = {
        "prefeitura_marilia", "ibge", "osmnx", "sinapi", "cepea_esalq",
        "tjsp", "diario_oficial", "snis", "datajud", "cnefe",
    }
    CONTRACT_SOURCES = {
        "uniao_imobiliaria", "toca_imoveis", "gemini_api",
        "vertex_ai", "google_maps",
    }

    if source_system in PUBLIC_SOURCES:
        return "dado_publico"
    if source_system in CONTRACT_SOURCES:
        return "contrato"
    return "legitimo_interesse"


def _infer_transfer_safeguard(source_system: str) -> Optional[str]:
    """Infere salvaguarda de transferência internacional."""
    from src.llm import get_llm_mode
    if source_system in ("gemini_api", "vertex_ai", "google_maps"):
        mode = get_llm_mode()
        return "vertex_ai_dpa" if mode == "vertex_ai" else None
    return None


def _calculate_retention(source_system: str, legal_basis: str) -> Optional[date]:
    """Calcula data de expiração baseada na política de retenção."""
    try:
        from src.db import get_client
        with _cache_lock:
            global _cache_loaded
            if not _cache_loaded:
                db = get_client()
                result = db.table("data_retention_policies").select(
                    "source_system, retention_days"
                ).execute()
                for row in result.data or []:
                    _retention_cache[row["source_system"]] = row["retention_days"]
                _cache_loaded = True

        days = _retention_cache.get(source_system)
        if days is None:
            days = DEFAULT_RETENTION_DAYS.get(legal_basis, 730)

        if days == -1:
            return None  # Retenção indefinida

        return date.today() + timedelta(days=days)

    except Exception:
        return None


def audit_llm_call(
    model: str,
    pipeline_step: str,
    records_count: int = 1,
    run_id: Optional[int] = None,
) -> None:
    """Shortcut para auditar chamadas ao LLM (sempre transferência internacional)."""
    from src.llm import get_llm_mode
    mode = get_llm_mode()
    log_data_flow(
        pipeline_step=pipeline_step,
        data_type="enrichment",
        source_system="gemini_api",
        records_count=records_count,
        agent_name=model,
        legal_basis="contrato",
        external_transfer=True,
        transfer_safeguard="vertex_ai_dpa" if mode == "vertex_ai" else None,
        contains_pii=False,
        run_id=run_id,
        metadata={"model": model, "llm_mode": mode},
    )
