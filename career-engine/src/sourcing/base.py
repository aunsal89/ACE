"""Abstract base interface for all sourcing scrapers and API clients."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from src.database.models import JobListingCreate
from src.config import SourcingSettings, TenantProfile


class BaseScraper(ABC):
    """Base scraper contract for external career portals, APIs, and aggregators."""

    def __init__(self, settings: SourcingSettings, tenant: TenantProfile):
        self.settings = settings
        self.tenant = tenant
        self.source_name: str = self.__class__.__name__.lower()

    @abstractmethod
    def fetch_raw_listings(self) -> List[Dict[str, Any]]:
        """Poll the remote portal or API and return raw listing payloads."""
        pass

    @abstractmethod
    def parse_listing(self, raw_data: Dict[str, Any]) -> Optional[JobListingCreate]:
        """Parse and normalize a single raw listing into a validated JobListingCreate model."""
        pass

    def run(self) -> List[JobListingCreate]:
        """Execute full pipeline: fetch -> parse -> return standardized job listings."""
        raw_items = self.fetch_raw_listings()
        standardized_jobs: List[JobListingCreate] = []
        for raw in raw_items:
            try:
                parsed = self.parse_listing(raw)
                if parsed:
                    standardized_jobs.append(parsed)
            except Exception:
                continue
        return standardized_jobs
