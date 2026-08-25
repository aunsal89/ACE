"""Opportunity Evaluation & Scoring Engine."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from rich.table import Table

from src.config import EngineConfig, TenantProfile, load_engine_config, load_tenant_profile
from src.database.models import (
    JobListing,
    JobStatus,
    RecommendationType,
    ScoringEvaluation,
    ScoringEvaluationCreate,
    TrackType,
)
from src.database.repository import JobRepository
from src.scoring.base import BaseScorer
from src.scoring.llm_client import ScoringLLMClient
from src.utils.logger import console, logger


class OpportunityScorer(BaseScorer):
    """Evaluates discovered job listings against dual-track tenant criteria."""

    def __init__(self, config: Optional[EngineConfig] = None, tenant: Optional[TenantProfile] = None):
        self.config = config or load_engine_config()
        self.tenant = tenant or load_tenant_profile(config=self.config)
        super().__init__(self.tenant)
        self.repo = JobRepository(self.config.database.db_path)
        self.llm_client = ScoringLLMClient(self.config.llm, self.tenant)

    def evaluate(self, job: JobListing) -> ScoringEvaluationCreate:
        """Score a single job listing and return a ScoringEvaluationCreate model."""
        eval_dict = self.llm_client.evaluate_fit(job)

        return ScoringEvaluationCreate(
            job_id=job.id,
            tenant_id=self.tenant.tenant_id,
            track=eval_dict["track"],
            overall_score=float(eval_dict["overall_score"]),
            comp_score=float(eval_dict.get("comp_score", 0)),
            location_score=float(eval_dict.get("location_score", 0)),
            tech_stack_score=float(eval_dict.get("tech_stack_score", 0)),
            leadership_score=float(eval_dict.get("leadership_score", 0)),
            fits_criteria=bool(eval_dict["fits_criteria"]),
            reasoning=eval_dict.get("reasoning", ""),
            matched_keywords=eval_dict.get("matched_keywords", []),
            missing_keywords=eval_dict.get("missing_keywords", []),
            recommendation=RecommendationType(eval_dict["recommendation"]),
            model_used=eval_dict.get("model_used", "scoring_engine")
        )

    def run_scoring_batch(self, job_id: Optional[str] = None, auto_queue: bool = True) -> List[ScoringEvaluation]:
        """
        Evaluate jobs in DISCOVERED state.
        Transitions scored jobs to QUEUED (if recommendation == QUEUE), REJECTED, or EVALUATED.
        """
        if job_id:
            job = self.repo.get_job_by_id(job_id)
            jobs = [job] if job else []
        else:
            jobs = self.repo.list_jobs(status=JobStatus.DISCOVERED, limit=100)

        if not jobs:
            console.print("[yellow]No DISCOVERED jobs awaiting evaluation.[/yellow]")
            return []

        console.print(f"[bold cyan]Evaluating {len(jobs)} Opportunities for Tenant:[/bold cyan] [yellow]{self.tenant.name}[/yellow]")
        evaluated_records: List[ScoringEvaluation] = []

        table = Table(title="Opportunity Evaluation Results", show_header=True, header_style="bold magenta")
        table.add_column("Company", style="green")
        table.add_column("Title", style="bold")
        table.add_column("Track", style="yellow")
        table.add_column("Fit Score", justify="right", style="bold")
        table.add_column("Recommendation", style="bold")
        table.add_column("Next State", style="cyan")

        for j in jobs:
            eval_create = self.evaluate(j)
            saved_eval = self.repo.save_evaluation(eval_create)
            evaluated_records.append(saved_eval)

            # Determine new status
            if auto_queue and saved_eval.recommendation == RecommendationType.QUEUE:
                new_status = JobStatus.QUEUED
                notes = f"Auto-queued with fit score {saved_eval.overall_score:.1f}/100"
            elif saved_eval.recommendation == RecommendationType.REJECT:
                new_status = JobStatus.REJECTED
                notes = "Criteria filtered out"
            else:
                new_status = JobStatus.EVALUATED
                notes = "Scored and awaiting manual review"

            self.repo.update_job_status(j.id, new_status, tenant_id=self.tenant.tenant_id, notes=notes)

            rec_color = "green" if saved_eval.recommendation == RecommendationType.QUEUE else "red" if saved_eval.recommendation == RecommendationType.REJECT else "yellow"
            table.add_row(
                j.company[:20],
                j.title[:30],
                saved_eval.track,
                f"{saved_eval.overall_score:.1f}",
                f"[{rec_color}]{saved_eval.recommendation.value}[/{rec_color}]",
                new_status.value
            )

        console.print(table)
        return evaluated_records
