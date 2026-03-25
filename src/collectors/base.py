"""Base class for all collectors."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from src.db import get_client

logger = logging.getLogger(__name__)


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
        self._run_id: int | None = None

    async def run(self) -> dict[str, int]:
        """Execute the full collection pipeline."""
        self._start_run()
        try:
            items = await self.fetch_all()
            logger.info(f"[{self.source}] Fetched {len(items)} items")

            for item in items:
                try:
                    source_id = self.extract_source_id(item)
                    self._upsert_raw(source_id, item)
                    self.stats["processed"] += 1
                except Exception:
                    self.stats["failed"] += 1
                    logger.exception(f"[{self.source}] Failed to process item")

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

    def _upsert_raw(self, source_id: str, raw_data: dict[str, Any]) -> None:
        """Insert or update a raw listing."""
        result = (
            self.db.table("raw_listings")
            .upsert(
                {
                    "source": self.source,
                    "source_id": source_id,
                    "raw_data": raw_data,
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                    "processed": False,
                },
                on_conflict="source,source_id",
            )
            .execute()
        )
        # Check if it was an insert or update
        if result.data:
            self.stats["created"] += 1

    def _start_run(self) -> None:
        """Log the start of a collector run."""
        result = (
            self.db.table("agent_runs")
            .insert({"agent_name": f"collector_{self.source}", "status": "running"})
            .execute()
        )
        if result.data:
            self._run_id = result.data[0]["id"]

    def _finish_run(self, status: str, error: str | None = None) -> None:
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
