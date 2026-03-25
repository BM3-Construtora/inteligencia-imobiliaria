"""MaríliaBot — Orquestrador principal."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Optional, List

from src.collectors.uniao import UniaoCollector
from src.collectors.toca import TocaCollector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mariliabot")

COLLECTORS = {
    "uniao": UniaoCollector,
    "toca": TocaCollector,
}

USAGE = """
MaríliaBot — Inteligência Imobiliária

Uso: python -m src.main <comando> [args]

Comandos:
  collect [source ...]   Roda coletores (todos se nenhum especificado)
  normalize              Normaliza raw_listings → listings
  pipeline               Roda collect + normalize em sequência
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


async def run_pipeline(collector_names: Optional[List[str]] = None) -> None:
    """Run full pipeline: collect → normalize."""
    await run_collectors(collector_names)
    run_normalize()


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
    elif command == "pipeline":
        names = args[1:] if len(args) > 1 else None
        asyncio.run(run_pipeline(names))
    else:
        print(f"Comando desconhecido: {command}")
        print(USAGE)


if __name__ == "__main__":
    main()
