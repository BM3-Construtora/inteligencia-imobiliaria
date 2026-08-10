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
# imovelweb collector retired 2026-05-11: Cloudflare blocks ~100% of requests
# from src.collectors.imovelweb import ImovelwebCollector
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
    "zapimoveis": ZapImoveisCollector,
}

RETIRED_COLLECTORS = {"imovelweb"}

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
  llm-cost [dias]        Relatório de custo de LLM (tokens + USD, default 30d)
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
  canon-bairros          Canonicaliza nomes de bairros existentes (one-shot LLM)
  projects <sub>         CLI de company_projects (add|list|update|set-outcome)
  off-market [src ...]   Coleta sinais off-market (leilao_caixa|iptu|alvara|inventario)
  itbi                   Coleta transações de ITBI (preço real de venda) Marília-SP
  habite-se              Coleta habite-se via API DOM-MAR (dados-abertos, sem LAI)
  iptu-planta            Coleta planta genérica de valores IPTU (LC 672/2013)
  labor                  Coleta índices SIDRA PNAD-C (rendimento/ocupados construção SP)
  construction-timeline  Join alvará × habite-se → prazo/custo real por bairro
  obras                  Coleta obras públicas municipais (API dados-abertos, 2017-atual)
  receitas               Coleta ITBI + Taxa de Licença de Obras mensais (transparência, 2021-atual)
  parcelamento           Coleta parcelamentos de solo aprovados no DOM-MAR
  licitacoes             Coleta licitações de obras públicas (API dados-abertos, 2020-atual)
  distress               Scora sinais off-market + envia top 5 Telegram
  regulatory             Avalia signals regulatorios (zoneamento/APP/vendedor)
  vision [N]             Computer Vision satelite (default 50 listings)
  zoning-parse           Parse plano diretor Marilia -> zoning_zones
  deals <sub>            CLI de bm3_deals (add|update|outcome|list|import-stalled)
  calibration            Roda feedback loop (Hunter/AVM/Viability drift)
  drift-report           Envia weekly drift report via Telegram
  osm                    Coleta POIs via OpenStreetMap/Overpass API
  alvara                 Coleta alvarás de aprovação DOM-MAR (Seção III-A, 18-36mo ahead)
  eiv                    Coleta EIVs (Estudo de Impacto de Vizinhança) DOM-MAR
  ibge-sectors           Coleta setores censitários IBGE 2022 (GeoJSON + renda)
  spatial-enrich         Enriquece listings com proximidade a POIs e score MCMV
  rating-construtoras    Calcula rating A/B/C/D de construtoras (dados DOM-MAR)
  cmdu                   Coleta atas do CMDU (decisões urbanísticas 6-12mo ahead)
  plano-diretor          Monitora DOM-MAR para keywords de upzoning/zoneamento
  cnpj-construtoras      Enriquece construtoras_rating com dados CNPJ/Receita Federal
  agronegocio            Coleta índice CEPEA ESALQ-USP (correlação safra × imóveis)
  heritage               Detector de herança: obituários × TJSP × listings
  embed                  Gera embeddings text-embedding-004 para listings e documentos
  vision-listings        Analisa fotos de anúncios via Gemini Vision (conservation score)
  health-check           Inspeciona agent_runs (24h) e alerta no Telegram se coletor quebrou
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
        if names:
            retired = [n for n in names if n in RETIRED_COLLECTORS]
            for n in retired:
                logger.warning(
                    f"{n} collector retired — pulando. See sql/data analysis: 0/177 active."
                )
            names = [n for n in names if n not in RETIRED_COLLECTORS]
            if not names:
                raise SystemExit(
                    "Nenhum collector válido: todos os solicitados estão aposentados."
                )
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
    elif command == "labor":
        from src.collectors.labor_sidra import run_collector as run_labor_collector
        logger.info("=== Starting LABOR SIDRA collector ===")
        s = run_labor_collector()
        logger.info(
            f"=== LABOR done: processed={s['processed']} "
            f"created={s['created']} failed={s['failed']} ==="
        )
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
    elif command == "canon-bairros":
        from src.enricher_llm import run_canonicalize_neighborhoods
        logger.info("=== Starting canonicalize-neighborhoods ===")
        s = run_canonicalize_neighborhoods()
        logger.info(
            f"=== Canon done: {s['original_count']} → {s['canonical_count']} bairros, "
            f"{s['merged_count']} merged, {s.get('deleted', 0)} deleted ==="
        )
    elif command == "projects":
        from src.projects_cli import main as projects_main
        raise SystemExit(projects_main(args[1:]))
    elif command == "off-market":
        names = args[1:] if len(args) > 1 else ["leilao_caixa", "iptu", "alvara", "inventario"]
        mapping = {
            "leilao_caixa": "src.collectors.off_market.leilao_caixa",
            "leilao_generico": "src.collectors.off_market.leilao_generico",
            "iptu": "src.collectors.off_market.iptu_devedor",
            "alvara": "src.collectors.off_market.alvara_prefeitura",
            "inventario": "src.collectors.off_market.inventario_tjsp",
        }
        for n in names:
            mod = mapping.get(n)
            if not mod:
                logger.warning(f"Unknown off-market source: {n}")
                continue
            try:
                m = __import__(mod, fromlist=["run_collector"])
                logger.info(f"=== Starting off-market collector: {n} ===")
                s = m.run_collector()
                logger.info(f"=== {n} done: {s} ===")
            except Exception:
                logger.exception(f"=== {n} FAILED ===")
    elif command == "itbi":
        from src.collectors import itbi_marilia
        logger.info("=== Starting ITBI Marília collector ===")
        s = itbi_marilia.run_collector()
        logger.info(f"=== itbi done: {s} ===")
    elif command == "habite-se":
        from src.collectors.habite_se_marilia import run_collector as run_habite_se
        logger.info("=== Starting Habite-se collector (DOM-MAR) ===")
        s = run_habite_se()
        logger.info(f"=== habite-se done: {s} ===")
    elif command == "iptu-planta":
        from src.collectors.iptu_planta_marilia import run_collector as run_iptu_planta
        logger.info("=== Starting IPTU Planta Genérica collector ===")
        s = run_iptu_planta()
        logger.info(f"=== iptu-planta done: {s} ===")
    elif command == "labor":
        from src.collectors.labor_sidra import run_collector as run_labor
        logger.info("=== Starting LABOR SIDRA collector ===")
        s = run_labor()
        logger.info(f"=== labor done: {s} ===")
    elif command == "construction-timeline":
        from src.construction_timeline import run_join_analyzer
        logger.info("=== Starting construction timeline analyzer ===")
        s = run_join_analyzer()
        logger.info(f"=== construction-timeline done: {s} ===")
    elif command == "obras":
        from src.collectors.obras_publicas_marilia import run_collector as run_obras
        logger.info("=== Starting Obras Públicas Marília collector ===")
        s = run_obras()
        logger.info(f"=== obras done: {s} ===")
    elif command == "receitas":
        from src.collectors.receitas_marilia import run_collector as run_receitas
        logger.info("=== Starting Receitas Marília collector ===")
        s = run_receitas()
        logger.info(f"=== receitas done: {s} ===")
    elif command == "parcelamento":
        from src.collectors.parcelamento_solo_marilia import run_collector as run_parcelamento
        logger.info("=== Starting Parcelamento de Solo collector ===")
        s = run_parcelamento()
        logger.info(f"=== parcelamento done: {s} ===")
    elif command == "licitacoes":
        from src.collectors.licitacoes_obras_marilia import run_collector as run_licitacoes
        logger.info("=== Starting Licitações de Obras collector ===")
        s = run_licitacoes()
        logger.info(f"=== licitacoes done: {s} ===")
    elif command == "distress":
        from src.distress import run_distress_scorer, send_daily_top_telegram
        logger.info("=== Starting distress scorer ===")
        s = run_distress_scorer()
        logger.info(f"=== Distress done: {s} ===")
        try:
            send_daily_top_telegram(5)
        except Exception:
            logger.exception("[distress] Telegram send failed")
    elif command == "regulatory":
        from src.regulatory import run_regulatory_scorer
        logger.info("=== Starting regulatory scorer ===")
        s = run_regulatory_scorer()
        logger.info(f"=== Regulatory done: {s} ===")
    elif command == "vision":
        from src.vision import run_vision_extractor
        limit = int(args[1]) if len(args) > 1 else 50
        logger.info(f"=== Starting vision extractor (limit={limit}) ===")
        s = run_vision_extractor(limit=limit)
        logger.info(f"=== Vision done: {s} ===")
    elif command == "zoning-parse":
        from src.collectors.zoning_marilia import parse_plano_diretor
        url = args[1] if len(args) > 1 else None
        logger.info("=== Starting zoning parser ===")
        n = parse_plano_diretor(url)
        logger.info(f"=== Zoning done: {n} zones ===")
    elif command == "deals":
        from src.deals_cli import main as deals_main
        raise SystemExit(deals_main(args[1:]))
    elif command == "calibration":
        from src.feedback_loop import run_calibration
        logger.info("=== Starting calibration ===")
        s = run_calibration()
        logger.info(f"=== Calibration done: {s} ===")
    elif command == "drift-report":
        from src.reporter_drift import run_weekly_drift_report
        logger.info("=== Starting drift report ===")
        s = run_weekly_drift_report()
        logger.info(f"=== Drift report done: {s} ===")
    elif command == "osm":
        from src.collectors.osm_collector import run_osm_collector
        logger.info("=== Starting OSM POI collector ===")
        s = run_osm_collector()
        logger.info(f"=== OSM done: {s} ===")
    elif command == "alvara":
        from src.collectors.alvara_marilia import run_alvara_collector
        logger.info("=== Starting Alvará collector (DOM-MAR Seção III-A) ===")
        s = run_alvara_collector()
        logger.info(f"=== alvara done: {s} ===")
    elif command == "eiv":
        from src.collectors.eiv_marilia import run_eiv_collector
        logger.info("=== Starting EIV collector ===")
        s = run_eiv_collector()
        logger.info(f"=== eiv done: {s} ===")
    elif command == "ibge-sectors":
        from src.collectors.ibge_sectors import run_ibge_sectors_collector
        logger.info("=== Starting IBGE Sectors collector ===")
        s = run_ibge_sectors_collector()
        logger.info(f"=== ibge-sectors done: {s} ===")
    elif command == "spatial-enrich":
        from src.spatial import run_proximity_enrichment
        logger.info("=== Starting spatial proximity enrichment ===")
        s = run_proximity_enrichment()
        logger.info(f"=== spatial-enrich done: {s} ===")
    elif command == "rating-construtoras":
        from src.rating_construtoras import run_rating_construtoras
        logger.info("=== Starting construtoras rating ===")
        s = run_rating_construtoras()
        logger.info(f"=== rating-construtoras done: {s} ===")
    elif command == "cmdu":
        from src.collectors.cmdu_atas import run_cmdu_collector
        logger.info("=== Starting CMDU atas collector ===")
        s = run_cmdu_collector()
        logger.info(f"=== cmdu done: {s} ===")
    elif command == "plano-diretor":
        from src.collectors.plano_diretor_monitor import run_plano_diretor_monitor
        logger.info("=== Starting Plano Diretor monitor ===")
        s = run_plano_diretor_monitor()
        logger.info(f"=== plano-diretor done: {s} ===")
    elif command == "cnpj-construtoras":
        from src.collectors.cnpj_construtoras import run_cnpj_enricher
        logger.info("=== Starting CNPJ enricher (construtoras) ===")
        s = run_cnpj_enricher()
        logger.info(f"=== cnpj-construtoras done: {s} ===")
    elif command == "agronegocio":
        from src.collectors.agronegocio import run_agronegocio_collector
        logger.info("=== Starting Agronegócio CEPEA collector ===")
        s = run_agronegocio_collector()
        logger.info(f"=== agronegocio done: {s} ===")
    elif command == "heritage":
        from src.collectors.heritage_detector import run_heritage_detector
        logger.info("=== Starting Heritage detector ===")
        s = run_heritage_detector()
        logger.info(f"=== heritage done: {s} ===")
    elif command == "embed":
        from src.embedder import run_embedder
        limit = int(args[1]) if len(args) > 1 else 500
        logger.info(f"=== Starting embedder (limit={limit}) ===")
        s = run_embedder(limit=limit)
        logger.info(f"=== embed done: {s} ===")
    elif command == "vision-listings":
        from src.vision_listings import run_vision_listings
        limit = int(args[1]) if len(args) > 1 else 100
        logger.info(f"=== Starting listing vision (limit={limit}) ===")
        s = run_vision_listings(limit=limit)
        logger.info(f"=== vision-listings done: {s} ===")
    elif command == "llm-cost":
        from src.llm_usage import report_usage
        days = int(args[1]) if len(args) > 1 else 30
        report_usage(days=days)
    elif command == "health-check":
        from src.health import run_health_check
        logger.info("=== Starting health-check ===")
        s = run_health_check()
        logger.info(
            f"=== health-check done: {s['checked']} agentes, "
            f"{s['problems']} problema(s) ==="
        )
    else:
        print(f"Comando desconhecido: {command}")
        print(USAGE)


if __name__ == "__main__":
    main()
