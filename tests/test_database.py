import sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

"""Unit tests for SQLite Database repository, state transitions, and audit logs."""

import unittest
from pathlib import Path
import tempfile
import os
from src.database.connection import init_db
from src.database.models import (
    JobListingCreate,
    JobStatus,
    PackageStatus,
    RecommendationType,
    ScoringEvaluationCreate,
    TrackType,
)
from src.database.repository import JobRepository
from src.utils.hashing import generate_deduplication_hash


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_career_engine.db"
        self.repo = JobRepository(self.db_path)
        tenant = self.repo.register_or_update_tenant(
            tenant_id="aunsal",
            name="Ahmet Halit Ünsal",
            email="aunsal89@gmail.com",
            config_path="config/tenants/aunsal/profile.yaml"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_upsert_job_and_deduplication(self):
        dedup_hash = generate_deduplication_hash("Baykar", "Lead Embedded Engineer", "Istanbul")
        job_in = JobListingCreate(
            deduplication_hash=dedup_hash,
            source="baykar",
            title="Lead Embedded Engineer",
            company="Baykar",
            location="Istanbul",
            assigned_track=TrackType.TRACK_A,
            status=JobStatus.DISCOVERED,
            description_raw="Developing EV powertrain ECU algorithms in Simulink."
        )

        job1, is_new1 = self.repo.upsert_job(job_in)
        self.assertTrue(is_new1)
        self.assertEqual(job1.status, JobStatus.DISCOVERED)

        # Re-upserting same hash should not duplicate
        job2, is_new2 = self.repo.upsert_job(job_in)
        self.assertFalse(is_new2)
        self.assertEqual(job1.id, job2.id)

    def test_status_transitions_and_history(self):
        dedup_hash = generate_deduplication_hash("Citadel", "Quant Developer", "London")
        job_in = JobListingCreate(
            deduplication_hash=dedup_hash,
            source="google_jobs",
            title="Quant Developer",
            company="Citadel",
            location="London",
            assigned_track=TrackType.TRACK_B,
            status=JobStatus.DISCOVERED
        )
        job, _ = self.repo.upsert_job(job_in)

        # Transition to EVALUATED
        j_eval = self.repo.update_job_status(job.id, JobStatus.EVALUATED, tenant_id="aunsal", notes="Passed automated filter")
        self.assertEqual(j_eval.status, JobStatus.EVALUATED)

        # Transition to QUEUED
        j_queued = self.repo.update_job_status(job.id, JobStatus.QUEUED, tenant_id="aunsal", notes="High score match")
        self.assertEqual(j_queued.status, JobStatus.QUEUED)

        # Check history audit trail
        history = self.repo.get_history_for_job(job.id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].from_status, "DISCOVERED")
        self.assertEqual(history[0].to_status, "EVALUATED")
        self.assertEqual(history[1].from_status, "EVALUATED")
        self.assertEqual(history[1].to_status, "QUEUED")

    def test_scoring_evaluation(self):
        dedup_hash = generate_deduplication_hash("Aselsan", "Head of Embedded Software", "Ankara")
        job_in = JobListingCreate(
            deduplication_hash=dedup_hash,
            source="aselsan",
            title="Head of Embedded Software",
            company="Aselsan",
            location="Ankara",
            assigned_track=TrackType.TRACK_A,
            status=JobStatus.DISCOVERED
        )
        job, _ = self.repo.upsert_job(job_in)

        eval_in = ScoringEvaluationCreate(
            job_id=job.id,
            tenant_id="aunsal",
            track="TRACK_A",
            overall_score=94.5,
            comp_score=90.0,
            location_score=100.0,
            tech_stack_score=95.0,
            leadership_score=95.0,
            fits_criteria=True,
            reasoning="Exceptional match for 15+ years experience, MBD, AUTOSAR, and defense electronics leadership.",
            matched_keywords=["MBD", "Simulink", "AUTOSAR", "ISO 26262", "Defense"],
            recommendation=RecommendationType.QUEUE,
            model_used="gemini-2.5-pro"
        )
        saved_eval = self.repo.save_evaluation(eval_in)
        self.assertEqual(saved_eval.overall_score, 94.5)
        self.assertTrue(saved_eval.fits_criteria)

        evals = self.repo.get_evaluations_for_job(job.id)
        self.assertEqual(len(evals), 1)

    def test_stats_aggregation(self):
        stats = self.repo.get_stats()
        self.assertIn("total_jobs", stats)
        self.assertIn("status_breakdown", stats)


if __name__ == "__main__":
    unittest.main()
