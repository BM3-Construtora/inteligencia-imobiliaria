"""RAG regulatório — responde perguntas sobre documentos municipais.

Recupera trechos de `document_embeddings` (CMDU, alvarás, EIVs, Plano Diretor)
via busca semântica (pgvector) e sintetiza uma resposta ancorada nos trechos,
com citações. Se o LLM não estiver disponível, degrada para listar os trechos
recuperados (retrieval-only). Nunca levanta exceção.
"""

from __future__ import annotations

import logging

from src.db import get_client
from src.embedder import search_documents

logger = logging.getLogger(__name__)

# source_table → rótulo legível para citação
_SOURCE_LABELS = {
    "cmdu_atas": "Ata do CMDU",
    "eiv_marilia": "EIV",
    "alvaras_marilia": "Alvará",
    "plano_diretor": "Plano Diretor",
    "plano_diretor_signals": "Plano Diretor",
}

TOP_K = 6
CONTEXT_CHARS = 500  # limite por trecho no prompt (controla custo de tokens)


def _label(source_table: str) -> str:
    return _SOURCE_LABELS.get(source_table, source_table or "Documento")


def _format_sources(hits: list[dict]) -> str:
    lines = ["📚 *Fontes:*"]
    for i, h in enumerate(hits, 1):
        label = _label(h.get("source_table", ""))
        sid = h.get("source_id") or "?"
        sim = h.get("similarity")
        sim_s = f" (sim {float(sim):.2f})" if isinstance(sim, (int, float)) else ""
        lines.append(f"[{i}] {label} — {sid}{sim_s}")
    return "\n".join(lines)


def _retrieval_only(question: str, hits: list[dict]) -> str:
    """Resposta sem síntese: mostra os trechos recuperados."""
    lines = [f"🔎 Trechos regulatórios sobre: *{question}*\n"]
    for i, h in enumerate(hits, 1):
        label = _label(h.get("source_table", ""))
        snippet = (h.get("chunk_text") or "").strip().replace("\n", " ")
        if len(snippet) > 300:
            snippet = snippet[:300] + "…"
        lines.append(f"[{i}] *{label}*: {snippet}")
        lines.append("")
    lines.append("_Síntese por IA indisponível — trechos brutos acima._")
    return "\n".join(lines)


def answer_regulatory_question(question: str) -> str:
    """Responde uma pergunta regulatória via RAG sobre documentos municipais."""
    question = (question or "").strip()
    if not question:
        return "Faça uma pergunta. Ex: `/regras posso construir prédio no Jardim América?`"

    db = get_client()
    hits = search_documents(db, question, top_k=TOP_K)

    if not hits:
        return (
            "🔎 Não encontrei base documental para essa pergunta nos documentos "
            "municipais indexados (CMDU, alvarás, EIV, Plano Diretor).\n"
            "_Reformule ou tente termos mais específicos._"
        )

    from src.llm import _generate, GEMINI_API_KEY

    if not GEMINI_API_KEY:
        return _retrieval_only(question, hits)

    context_blocks = []
    for i, h in enumerate(hits, 1):
        label = _label(h.get("source_table", ""))
        text = (h.get("chunk_text") or "").strip().replace("\n", " ")
        if len(text) > CONTEXT_CHARS:
            text = text[:CONTEXT_CHARS] + "…"
        context_blocks.append(f"[{i}] ({label}) {text}")
    context = "\n\n".join(context_blocks)

    prompt = (
        "Você é o MariliaBot, assistente regulatório de uma construtora em Marília-SP.\n"
        "Responda à pergunta USANDO SOMENTE os trechos de documentos oficiais abaixo.\n"
        "Se os trechos não contiverem a resposta, diga que não há base documental "
        "suficiente. Não invente artigos de lei, números ou zoneamentos que não "
        "estejam nos trechos. Cite as fontes pelo número entre colchetes, ex: [1].\n"
        "Responda em português, direto, máximo 250 palavras.\n\n"
        f"TRECHOS:\n{context}\n\n"
        f"PERGUNTA: {question}\n\nRESPOSTA:"
    )

    answer = _generate(prompt, max_tokens=900, thinking=True, task="rag_regulatorio")
    if not answer:
        return _retrieval_only(question, hits)

    return f"{answer}\n\n{_format_sources(hits)}"
