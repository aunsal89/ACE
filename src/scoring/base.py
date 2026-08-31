"""Abstract base interface for opportunity scoring and track matching."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from src.config import TenantProfile
from src.database.models import JobListing, ScoringEvaluationCreate


class BaseScorer(ABC):
    """Base evaluator contract for ranking opportunities against tenant profiles."""

    def __init__(self, tenant: TenantProfile):
        self.tenant = tenant

    @abstractmethod
    def evaluate(self, job: JobListing) -> Optional[ScoringEvaluationCreate]:
        """Score a job listing against Track A / Track B requirements."""
        pass
