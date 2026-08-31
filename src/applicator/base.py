"""Abstract base interface for generating tailored application packages."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from src.config import TenantProfile
from src.database.models import ApplicationPackageCreate, JobListing, ScoringEvaluation


class BaseApplicator(ABC):
    """Base contract for generating tailored CVs, Cover Letters, and LinkedIn copy into /inbox/."""

    def __init__(self, tenant: TenantProfile, inbox_dir: Path):
        self.tenant = tenant
        self.inbox_dir = inbox_dir
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def generate_package(
        self,
        job: JobListing,
        evaluation: ScoringEvaluation
    ) -> ApplicationPackageCreate:
        """Generate tailored application assets staged in /inbox/ for human review."""
        pass
