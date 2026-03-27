"""MaríliaBot — Orquestrador principal."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Optional, List

from src.collectors.uniao import UniaoCollector
from src.collectors.toca import TocaCollector
from src.collectors.vivareal import VivaRealCollector
from src.collectors.chavesnamao import ChavesNaMaoCollector
from src.collectors.imovelweb import ImovelwebCollector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mariliabot")

COLLECTORS = {
    "uniao": UniaoCollector,
    "toca": TocaCollector,
    "vivareal": VivaRealCollector,
    "chavesnamao": ChavesNaMaoCollector,
    "imovelweb": ImovelwebCollector,
}

USAGE = """
MaríliaBot — Inteligência Imobiliária

Uso: python -m src.main <comando> [args]

Comandos:
  collect [source ...]   Roda coletores (todos se nenhum especificado)
  normalize              Normaliza raw_listings → listings
  classify               Classifica listings por market tier (padrão)
  analyze                Gera market snapshots e atualiza bairros
  hunt                   Pontua terrenos e gera oportunidades
  dedup                  Deduplicação cross-portal
  enrich                 Geocoding de listings sem coordenadas
  enrich-llm             Enriquecimento com Gemini (atributos + bairros)
  trends                 Detecta tendências de preço por bairro
  score-llm              Second opinion LLM nas top oportunidades
  risk                   Avaliação de risco (zoneamento, legal, ambiental)
  viability              Simulação de viabilidade MCMV (4 cenários)
  notify                 Envia alertas Telegram para oportunidades
  report                 Relatório semanal de mercado via Telegram
  pipeline               Roda pipeline completo
""".strip()


async def run_collectors(names: Optional[List[str]] = None) -> None:
    """Run specified collectors (or all if none specified)."""
    targets = names or list(COLLECTORS.keys())

    for name in targets:
        cls = COLLECTORS.get(name)
        if not cls:
            logger.error(f"Unknown collector: {name}")
            continue

        logger.info(f"=== Starting collector: {name} ===")
        collector = cls()
        try:
            stats = await collector.run()
            logger.info(
                f"=== {name} done: "
                f"{stats['processed']} processed, "
                f"{stats['created']} created, "
                f"{stats['failed']} failed ==="
            )
        except Exception:
            logger.exception(f"=== {name} FAILED ===")


def run_normalize() -> None:
    """Run the normalizer."""
    from src.normalizer import run_normalizer

    logger.info("=== Starting normalizer ===")
    stats = run_normalizer()
    logger.info(
        f"=== Normalizer done: "
        f"{stats['processed']} processed, "
        f"{stats['created']} created, "
        f"{stats['updated']} updated, "
        f"{stats['price_changes']} price changes, "
        f"{stats['failed']} failed ==="
    )


def run_analyze() -> None:
    """Run the analyst."""
    from src.analyst import run_analyst

    logger.info("=== Starting analyst ===")
    stats = run_analyst()
    logger.info(
        f"=== Analyst done: "
        f"{stats['snapshots']} snapshots, "
        f"{stats['neighborhoods']} neighborhoods ==="
    )


def run_hunt() -> None:
    """Run the hunter."""
    from src.hunter import run_hunter

    logger.info("=== Starting hunter ===")
    stats = run_hunter()
    logger.info(
        f"=== Hunter done: "
        f"{stats['scored']} scored, "
        f"{stats['opportunities']} opportunities, "
        f"top score: {stats['top_score']:.1f} ==="
    )


def run_notify() -> None:
    """Run the notifier."""
    from src.notifier import run_notifier

    logger.info("=== Starting notifier ===")
    stats = run_notifier()
    logger.info(f"=== Notifier done: {stats['notified']} sent ===")


def run_classify() -> None:
    """Run the classifier."""
    from src.classifier import run_classifier

    logger.info("=== Starting classifier ===")
    stats = run_classifier()
    logger.info(
        f"=== Classifier done: "
        f"{stats['classified']} classified, "
        f"{stats['skipped']} skipped ==="
    )


async def run_pipeline(collector_names: Optional[List[str]] = None) -> None:
    """Run full pipeline: collect → normalize → classify → analyze → hunt → notify."""
    await run_collectors(collector_names)
    run_normalize()
    run_classify()
    run_analyze()
    run_hunt()
    run_notify()


def main() -> None:
    """CLI entry point."""
    args = sys.argv[1:]

    if not args:
        print(USAGE)
        return

    command = args[0]

    if command == "collect":
        names = args[1:] if len(args) > 1 else None
        asyncio.run(run_collectors(names))
    elif command == "normalize":
        run_normalize()
    elif command == "classify":
        run_classify()
    elif command == "analyze":
        run_analyze()
    elif command == "hunt":
        run_hunt()
    elif command == "dedup":
        from src.deduplicator import run_deduplicator
        logger.info("=== Starting deduplicator ===")
        s = run_deduplicator()
        logger.info(f"=== Dedup done: {s['matches']} matches ({s['high_confidence']} high confidence) ===")
    elif command == "enrich":
        from src.enricher import run_enricher
        logger.info("=== Starting enricher ===")
        s = run_enricher()
        logger.info(f"=== Enricher done: {s['geocoded']} geocoded of {s['processed']} ===")
    elif command == "enrich-llm":
        from src.enricher_llm import run_llm_enricher
        logger.info("=== Starting LLM enricher ===")
        s = run_llm_enricher()
        logger.info(f"=== LLM Enricher done: {s['enriched']} enriched, {s['neighborhoods_normalized']} neighborhoods ===")
    elif command == "trends":
        from src.trends import run_trends
        logger.info("=== Starting trends ===")
        s = run_trends()
        logger.info(f"=== Trends done: {s['aquecendo']} aquecendo, {s['esfriando']} esfriando, {s['estavel']} estavel ===")
    elif command == "score-llm":
        from src.scorer_llm import run_llm_scorer
        logger.info("=== Starting LLM scorer ===")
        s = run_llm_scorer()
        logger.info(f"=== LLM Scorer done: {s['scored']} scored ===")
    elif command == "risk":
        from src.risk_scorer import run_risk_scorer
        logger.info("=== Starting risk scorer ===")
        s = run_risk_scorer()
        logger.info(f"=== Risk done: {s['assessed']} assessed, {s['high_risk']} high risk ===")
    elif command == "viability":
        from src.viability import run_viability
        logger.info("=== Starting viability ===")
        s = run_viability()
        logger.info(f"=== Viability done: {s['viable']} viable of {s['analyzed']} ===")
    elif command == "notify":
        from src.notifier import run_notifier
        logger.info("=== Starting notifier ===")
        s = run_notifier()
        logger.info(f"=== Notifier done: {s['notified']} sent ===")
    elif command == "report":
        from src.reporter import run_weekly_report
        logger.info("=== Starting weekly report ===")
        s = run_weekly_report()
        logger.info(f"=== Report done: {s['sent']} sent ===")
    elif command == "pipeline":
        names = args[1:] if len(args) > 1 else None
        asyncio.run(run_pipeline(names))
    else:
        print(f"Comando desconhecido: {command}")
        print(USAGE)


if __name__ == "__main__":
    main()
