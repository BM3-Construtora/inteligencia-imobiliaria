"""Parser de tabelas de preço em PDF via Gemini.

Uso típico — tabela Tigre/Amanco:
    python -m src.materials.pdf_parser \\
        --supplier tigre_tubos \\
        --pdf /tmp/tabela_tigre_maio2026.pdf \\
        --category tubulacao --unit un

Ou via código:
    from src.materials.pdf_parser import parse_and_persist
    results = parse_and_persist(
        supplier_slug="tigre_tubos",
        pdf_source="/tmp/tabela.pdf",  # path local ou URL https://
        category="tubulacao",
        unit="un",
    )

O Gemini recebe até 10 páginas em base64 (PDF inline) com prompt estruturado.
Retorna JSON com lista de {product, unit, price, brand, ean, note}.
Persiste via manual_quote.submit() com source='pdf'.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models"
    f"/{GEMINI_MODEL}:generateContent"
)

MAX_PAGES_PER_CALL = 10


def parse_pdf(pdf_source: str | Path) -> list[dict[str, Any]]:
    """Extrai tabela de preços de PDF. Retorna lista de dicts com campos raw.

    Cada dict pode conter: product (str), unit (str|None), price (float|None),
    brand (str|None), ean (str|None), note (str|None).
    """
    if not GEMINI_API_KEY:
        raise EnvironmentError("GEMINI_API_KEY não definida")

    pdf_bytes = _load_pdf(pdf_source)
    pdf_b64 = base64.b64encode(pdf_bytes).decode()

    prompt = (
        "Você recebeu uma tabela de preços de materiais de construção em PDF. "
        "Extraia TODOS os itens da tabela e retorne um objeto JSON com a chave "
        '"items" contendo uma lista. Cada item deve ter:\n'
        '  "product": nome completo do produto (string)\n'
        '  "unit": unidade de medida (un, m, m2, m3, kg, saco, rolo, etc.) ou null\n'
        '  "price": preço unitário como número float ou null\n'
        '  "brand": marca se disponível ou null\n'
        '  "ean": código EAN/barras se disponível ou null\n'
        '  "note": observação relevante (ex: frete, validade, mínimo) ou null\n\n'
        "Retorne APENAS o JSON válido, sem markdown, sem explicações."
    )

    payload = {
        "contents": [{
            "parts": [
                {
                    "inline_data": {
                        "mime_type": "application/pdf",
                        "data": pdf_b64,
                    }
                },
                {"text": prompt},
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }

    try:
        resp = httpx.post(
            GEMINI_ENDPOINT,
            params={"key": GEMINI_API_KEY},
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"Gemini API erro {e.response.status_code}: {e.response.text[:300]}") from e

    raw_text = _extract_gemini_text(resp.json())
    return _parse_gemini_response(raw_text)


def parse_and_persist(
    supplier_slug: str,
    pdf_source: str | Path,
    *,
    category: str,
    unit: str,
    dry_run: bool = False,
) -> dict[str, int]:
    """Parse PDF e persiste no banco via manual_quote.submit().

    Retorna stats: {parsed, persisted, skipped, errors}.
    """
    from src.materials.manual_quote import submit as manual_submit

    stats = {"parsed": 0, "persisted": 0, "skipped": 0, "errors": 0}

    items = parse_pdf(pdf_source)
    stats["parsed"] = len(items)
    logger.info(f"[pdf_parser] {len(items)} itens extraídos de {pdf_source}")

    for item in items:
        product = item.get("product")
        price = item.get("price")

        if not product or not price:
            stats["skipped"] += 1
            continue

        if dry_run:
            logger.info(f"[pdf_parser] dry-run: {product} → R${price}")
            stats["persisted"] += 1
            continue

        try:
            manual_submit(
                supplier_slug=supplier_slug,
                canonical_name=product,
                category=category,
                unit=item.get("unit") or unit,
                price=float(price),
                brand=item.get("brand"),
                ean=item.get("ean"),
                note=item.get("note"),
            )
            stats["persisted"] += 1
        except Exception:
            logger.exception(f"[pdf_parser] persist falhou: {product}")
            stats["errors"] += 1

    return stats


def _load_pdf(source: str | Path) -> bytes:
    """Carrega PDF de path local ou URL."""
    src = str(source)
    if src.startswith("http://") or src.startswith("https://"):
        resp = httpx.get(src, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        return resp.content
    return Path(source).read_bytes()


def _extract_gemini_text(response: dict) -> str:
    try:
        return response["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Resposta Gemini inesperada: {response}") from e


def _parse_gemini_response(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    # Remove markdown fences se presentes
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON inválido do Gemini: {e}\nTexto: {text[:300]}") from e

    items = data if isinstance(data, list) else data.get("items", [])
    if not isinstance(items, list):
        raise RuntimeError(f"Estrutura inesperada do Gemini: {type(data)}")
    return items


def main() -> None:
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Parsear tabela de preço em PDF.")
    parser.add_argument("--supplier", required=True, help="slug do fornecedor")
    parser.add_argument("--pdf", required=True, help="path local ou URL do PDF")
    parser.add_argument("--category", required=True)
    parser.add_argument("--unit", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    stats = parse_and_persist(
        supplier_slug=args.supplier,
        pdf_source=args.pdf,
        category=args.category,
        unit=args.unit,
        dry_run=args.dry_run,
    )
    print(stats, file=sys.stdout)


if __name__ == "__main__":
    main()
