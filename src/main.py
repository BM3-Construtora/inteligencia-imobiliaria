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
from src.collectors.zapimoveis import ZapImoveisCollector

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
    "zapimoveis": ZapImoveisCollector,
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
  comps                  Análise de comparáveis para oportunidades
  alerts                 Checa saved searches e envia alertas
  price-model            Treina modelo de predição de preço (terrenos)
  sales                  Detecta vendas estimadas (listings removidos)
  heat                   Calcula indice de calor do mercado por bairro
  sinapi                 Busca custos de construção SINAPI/IBGE
  ibge                   Atualiza dados demográficos do IBGE
  bot                    Inicia o bot conversacional do Telegram
  creci                  Coleta dados agregados do CRECI-SP
  pipeline               Roda pipeline completo
""".strip()


def _run_collector_sync(name: str, cls: type) -> None:
    """Run a single collector synchronously (for use in threads)."""
    logger.info(f"=== Starting collector: {name} ===")
    collector = cls()
    try:
        stats = asyncio.run(collector.run())
        logger.info(
            f"=== {name} done: "
            f"{stats['processed']} processed, "
            f"{stats['created']} created, "
            f"{stats['failed']} failed ==="
        )
    except Exception:
        logger.exception(f"=== {name} FAILED ===")


async def run_collectors(names: Optional[List[str]] = None) -> None:
    """Run collectors in parallel using threads (scrapers are sync/blocking)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    targets = names or list(COLLECTORS.keys())

    valid = [(n, COLLECTORS[n]) for n in targets if n in COLLECTORS]
    if not valid:
        return

    # API collectors (uniao, toca) are fast → run first sequentially
    # HTML scrapers use cloudscraper (blocking) → run in parallel threads
    apis = [(n, c) for n, c in valid if n in ("uniao", "toca")]
    scrapers = [(n, c) for n, c in valid if n not in ("uniao", "toca")]

    # Run APIs sequentially — await directly since we're already in async context
    for name, cls in apis:
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

    # Run scrapers in parallel threads (each takes 30-60s with delays)
    if scrapers:
        logger.info(f"=== Running {len(scrapers)} scrapers in parallel ===")
        with ThreadPoolExecutor(max_workers=len(scrapers)) as executor:
            futures = {
                executor.submit(_run_collector_sync, name, cls): name
                for name, cls in scrapers
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    future.result()
                except Exception:
                    logger.exception(f"=== {name} thread FAILED ===")


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


def _run_step(name: str, fn) -> bool:
    """Run a pipeline step, return True if successful."""
    try:
        fn()
        return True
    except Exception:
        logger.exception(f"=== Pipeline step '{name}' FAILED — halting ===")
        return False


def _run_optional_step(name: str, fn) -> None:
    """Run an optional pipeline step, log but don't halt on failure."""
    try:
        fn()
    except Exception:
        logger.exception(f"=== Optional step '{name}' failed, continuing ===")


async def run_pipeline(collector_names: Optional[List[str]] = None) -> None:
    """Run full pipeline — mirrors GitHub Actions workflow exactly."""
    import time
    t0 = time.time()

    # Phase 1: Collect
    await run_collectors(collector_names)

    # Phase 2: Normalize + Classify (critical — halt on failure)
    if not _run_step("normalize", run_normalize):
        return
    if not _run_step("classify", run_classify):
        return

    # Phase 2b: Enrich (optional — LLM may not be configured)
    def _enrich_llm():
        from src.enricher_llm import run_llm_enricher
        logger.info("=== Starting LLM enricher ===")
        s = run_llm_enricher()
        logger.info(f"=== LLM Enricher done: {s['enriched']} enriched ===")
    _run_optional_step("enrich-llm", _enrich_llm)

    # Phase 3: Dedup
    def _dedup():
        from src.deduplicator import run_deduplicator
        logger.info("=== Starting deduplicator ===")
        s = run_deduplicator()
        logger.info(f"=== Dedup done: {s['matches']} matches ===")
    _run_optional_step("dedup", _dedup)

    # Phase 4: Analyze + Intelligence (critical)
    if not _run_step("analyze", run_analyze):
        return

    def _trends():
        from src.trends import run_trends
        logger.info("=== Starting trends ===")
        s = run_trends()
        logger.info(f"=== Trends done: {s['aquecendo']} aquecendo, {s['esfriando']} esfriando ===")

    def _sales():
        from src.sales_tracker import run_sales_tracker
        logger.info("=== Starting sales tracker ===")
        s = run_sales_tracker()
        logger.info(f"=== Sales done: {s['recorded']} recorded ===")

    def _heat():
        from src.market_heat import run_market_heat
        logger.info("=== Starting market heat ===")
        s = run_market_heat()
        logger.info(f"=== Heat done: {s['hot']} hot, {s['cold']} cold ===")

    _run_optional_step("trends", _trends)
    _run_optional_step("sales", _sales)
    _run_optional_step("heat", _heat)

    # Phase 5: Score + Risk + Viability (critical: hunt)
    if not _run_step("hunt", run_hunt):
        return

    def _score_llm():
        from src.scorer_llm import run_llm_scorer
        logger.info("=== Starting LLM scorer ===")
        s = run_llm_scorer()
        logger.info(f"=== LLM Scorer done: {s['scored']} scored ===")

    def _risk():
        from src.risk_scorer import run_risk_scorer
        logger.info("=== Starting risk scorer ===")
        s = run_risk_scorer()
        logger.info(f"=== Risk done: {s['assessed']} assessed ===")

    def _viability():
        from src.viability import run_viability
        logger.info("=== Starting viability ===")
        s = run_viability()
        logger.info(f"=== Viability done: {s['viable']} viable of {s['analyzed']} ===")

    def _comps():
        from src.comps import run_comps_for_opportunities
        logger.info("=== Starting comparables ===")
        s = run_comps_for_opportunities()
        logger.info(f"=== Comps done: {s['with_comps']} with comps ===")

    _run_optional_step("score-llm", _score_llm)
    _run_optional_step("risk", _risk)
    _run_optional_step("viability", _viability)
    _run_optional_step("comps", _comps)

    # Notify/alerts removidos do pipeline diário — consolidados no relatório semanal
    # (segunda-feira 9h BRT via weekly-report.yml)

    elapsed = time.time() - t0
    logger.info(f"=== Pipeline complete in {elapsed:.0f}s ({elapsed/60:.1f}min) ===")


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
    elif command == "comps":
        from src.comps import run_comps_for_opportunities
        logger.info("=== Starting comparables ===")
        s = run_comps_for_opportunities()
        logger.info(f"=== Comps done: {s['with_comps']} with comps of {s['processed']} ===")
    elif command == "alerts":
        from src.alerts import run_alerts
        logger.info("=== Starting alerts ===")
        s = run_alerts()
        logger.info(f"=== Alerts done: {s['matches']} matches, {s['notified']} notified ===")
    elif command == "price-model":
        from src.price_model import run_price_model
        logger.info("=== Starting price model ===")
        s = run_price_model()
        logger.info(f"=== Price model done: {s['predicted']} predicted, {s['undervalued']} undervalued ===")
    elif command == "sales":
        from src.sales_tracker import run_sales_tracker
        logger.info("=== Starting sales tracker ===")
        s = run_sales_tracker()
        logger.info(f"=== Sales done: {s['recorded']} recorded of {s['detected']} detected ===")
    elif command == "heat":
        from src.market_heat import run_market_heat
        logger.info("=== Starting market heat ===")
        s = run_market_heat()
        logger.info(f"=== Heat done: {s['neighborhoods']} scored, {s['hot']} hot, {s['cold']} cold ===")
    elif command == "sinapi":
        from src.collectors.sinapi import run_sinapi_collector
        logger.info("=== Starting SINAPI collector ===")
        s = run_sinapi_collector()
        logger.info(f"=== SINAPI done: {s['metrics']} metrics ===")
    elif command == "ibge":
        from src.ibge import run_ibge_update
        logger.info("=== Starting IBGE update ===")
        s = run_ibge_update()
        logger.info(f"=== IBGE done: {s['metrics']} metrics ===")
    elif command == "bot":
        from src.telegram_bot import run_bot
        run_bot()
    elif command == "creci":
        from src.collectors.creci import run_creci_collector
        logger.info("=== Starting CRECI-SP collector ===")
        s = run_creci_collector()
        logger.info(f"=== CRECI done: {s['metrics_extracted']} metrics ===")
    elif command == "pipeline":
        names = args[1:] if len(args) > 1 else None
        asyncio.run(run_pipeline(names))
    else:
        print(f"Comando desconhecido: {command}")
        print(USAGE)


if __name__ == "__main__":
    main()
