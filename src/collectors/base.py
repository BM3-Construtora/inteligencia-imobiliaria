"""Base class for all collectors."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from src.db import get_client

logger = logging.getLogger(__name__)

UPSERT_BATCH_SIZE = 200


class BaseCollector(ABC):
    """Base collector that handles raw_listings upsert and agent_runs logging."""

    source: str  # source_portal enum value

    def __init__(self) -> None:
        self.db = get_client()
        self.stats = {
            "processed": 0,
            "created": 0,
            "updated": 0,
            "failed": 0,
        }
        self._run_id: Optional[int] = None

    async def run(self) -> dict[str, int]:
        """Execute the full collection pipeline."""
        self._start_run()
        try:
            items = await self.fetch_all()
            logger.info(f"[{self.source}] Fetched {len(items)} items")

            # Batch upsert instead of per-item
            self._batch_upsert_raw(items)

            self._finish_run("completed")
        except Exception as e:
            self._finish_run("failed", str(e))
            raise
        return self.stats

    @abstractmethod
    async def fetch_all(self) -> list[dict[str, Any]]:
        """Fetch all items from the source. Must be implemented by subclasses."""
        ...

    @abstractmethod
    def extract_source_id(self, item: dict[str, Any]) -> str:
        """Extract the unique source ID from a raw item."""
        ...

    def _batch_upsert_raw(self, items: list[dict[str, Any]]) -> None:
        """Batch upsert raw listings for speed. Deduplicates within batch."""
        now = datetime.now(timezone.utc).isoformat()
        batch: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for item in items:
            try:
                source_id = self.extract_source_id(item)
                # Skip duplicates within the same batch
                if source_id in seen_ids:
                    continue
                seen_ids.add(source_id)

                batch.append({
                    "source": self.source,
                    "source_id": source_id,
                    "raw_data": item,
                    "collected_at": now,
                    "processed": False,
                })
            except Exception:
                self.stats["failed"] += 1
                logger.exception(f"[{self.source}] Failed to extract source_id")

            # Flush batch
            if len(batch) >= UPSERT_BATCH_SIZE:
                self._flush_batch(batch)
                batch = []
                seen_ids.clear()

        # Flush remaining
        if batch:
            self._flush_batch(batch)

    def _flush_batch(self, batch: list[dict[str, Any]]) -> None:
        """Upsert a batch of raw listings."""
        try:
            result = (
                self.db.table("raw_listings")
                .upsert(batch, on_conflict="source,source_id")
                .execute()
            )
            count = len(result.data) if result.data else len(batch)
            self.stats["processed"] += count
            self.stats["created"] += count
            logger.info(
                f"[{self.source}] Batch upserted {count} items "
                f"(total: {self.stats['processed']})"
            )
        except Exception:
            self.stats["failed"] += len(batch)
            logger.exception(f"[{self.source}] Batch upsert failed ({len(batch)} items)")

    def _start_run(self) -> None:
        """Log the start of a collector run."""
        result = (
            self.db.table("agent_runs")
            .insert({"agent_name": f"collector_{self.source}", "status": "running"})
            .execute()
        )
        if result.data:
            self._run_id = result.data[0]["id"]

    def _finish_run(self, status: str, error: Optional[str] = None) -> None:
        """Log the end of a collector run."""
        if not self._run_id:
            return
        update = {
            "status": status,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "items_processed": self.stats["processed"],
            "items_created": self.stats["created"],
            "items_updated": self.stats["updated"],
            "items_failed": self.stats["failed"],
        }
        if error:
            update["error_message"] = error[:1000]
        self.db.table("agent_runs").update(update).eq("id", self._run_id).execute()
