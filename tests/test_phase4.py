"""Unit tests for Phase 4: Scoring Engine, PDF Rendering & Application Drafting."""

import sys
from pathlib import Path
import unittest
import tempfile

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from src.config import load_engine_config, load_tenant_profile
from src.database.models import JobListingCreate, JobStatus, RecommendationType, TrackType
from src.database.repository import JobRepository
from src.scoring.scorer import OpportunityScorer
from src.applicator.generator import ApplicationGenerator
from src.utils.hashing import generate_deduplication_hash
from src.utils.pdf import render_markdown_to_pdf


from unittest.mock import patch


class TestPhase4(unittest.TestCase):
    def setUp(self):
        self.config = load_engine_config()
        self.tenant = load_tenant_profile(config=self.config)

    def test_pdf_renderer(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = Path(tmp_dir) / "test_cv.pdf"
            sample_md = """# Ahmet Halit Ünsal
## Embedded Software Director

* **Model-Based Design:** 15+ years experience in MATLAB/Simulink.
* **ISO 26262:** ASIL D functional safety leadership.
"""
            out = render_markdown_to_pdf(sample_md, pdf_path, doc_title="Test Document")
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 500)

    def test_scoring_engine_track_a(self):
        scorer = OpportunityScorer(config=self.config, tenant=self.tenant)
        job = JobListingCreate(
            deduplication_hash=generate_deduplication_hash("ASELSAN", "Embedded Software Director", "Ankara"),
            source="aselsan",
            title="Embedded Software Director (MBD / Powertrain)",
            company="ASELSAN",
            location="Ankara, Turkey",
            description_raw="Leading 30 engineers in Model-Based Design, Simulink, AUTOSAR, and ISO 26262 ASIL D.",
            assigned_track=TrackType.TRACK_A,
            status=JobStatus.DISCOVERED
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_db = Path(tmp_dir) / "test_score.db"
            repo = JobRepository(temp_db)
            repo.register_or_update_tenant(
                tenant_id=self.tenant.tenant_id,
                name=self.tenant.name,
                email=self.tenant.email,
                config_path=str(self.config.multi_tenancy.tenants_dir / self.tenant.tenant_id / "profile.yaml")
            )
            saved_job, _ = repo.upsert_job(job)

            with patch.object(scorer.llm_client, "evaluate_fit", side_effect=scorer.llm_client._evaluate_deterministic):
                evaluation = scorer.evaluate(saved_job)
                self.assertEqual(evaluation.track, "TRACK_A")
                self.assertGreaterEqual(evaluation.overall_score, 80.0)
                self.assertEqual(evaluation.recommendation, RecommendationType.QUEUE)
                self.assertTrue(evaluation.fits_criteria)

    def test_scoring_engine_track_b(self):
        scorer = OpportunityScorer(config=self.config, tenant=self.tenant)
        job = JobListingCreate(
            deduplication_hash=generate_deduplication_hash("Citadel", "Quant Developer", "London"),
            source="google_jobs",
            title="Quant Developer - Algorithmic Execution",
            company="Citadel",
            location="London, United Kingdom",
            description_raw="High-performance algorithmic execution, CCXT, Python, C++, and walk-forward optimization.",
            assigned_track=TrackType.TRACK_B,
            status=JobStatus.DISCOVERED
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_db = Path(tmp_dir) / "test_score_b.db"
            repo = JobRepository(temp_db)
            repo.register_or_update_tenant(
                tenant_id=self.tenant.tenant_id,
                name=self.tenant.name,
                email=self.tenant.email,
                config_path=str(self.config.multi_tenancy.tenants_dir / self.tenant.tenant_id / "profile.yaml")
            )
            saved_job, _ = repo.upsert_job(job)

            with patch.object(scorer.llm_client, "evaluate_fit", side_effect=scorer.llm_client._evaluate_deterministic):
                evaluation = scorer.evaluate(saved_job)
                self.assertEqual(evaluation.track, "TRACK_B")
                self.assertGreaterEqual(evaluation.overall_score, 80.0)
                self.assertEqual(evaluation.recommendation, RecommendationType.QUEUE)

    def test_application_generator(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_config = self.config.model_copy(deep=True)
            test_config.database.db_path = Path(tmp_dir) / "test_app.db"
            test_config.engine.inbox_dir = Path(tmp_dir) / "inbox"

            repo = JobRepository(test_config.database.db_path)
            repo.register_or_update_tenant(
                tenant_id=self.tenant.tenant_id,
                name=self.tenant.name,
                email=self.tenant.email,
                config_path=str(self.config.multi_tenancy.tenants_dir / self.tenant.tenant_id / "profile.yaml")
            )

            job = JobListingCreate(
                deduplication_hash=generate_deduplication_hash("Baykar", "Gömülü Aviyonik Lideri", "Istanbul"),
                source="baykar",
                title="Gömülü Aviyonik Lideri",
                company="Baykar",
                location="Istanbul",
                description_raw="Uçuş kontrol sistemleri, Simulink, MBD, C/C++.",
                assigned_track=TrackType.TRACK_A,
                status=JobStatus.QUEUED
            )
            saved_job, _ = repo.upsert_job(job)

            from src.database.models import ScoringEvaluationCreate
            eval_mock = ScoringEvaluationCreate(
                job_id=saved_job.id,
                tenant_id=self.tenant.tenant_id,
                track="TRACK_A",
                overall_score=92.0,
                skills_match_score=95.0,
                seniority_match_score=90.0,
                location_match_score=90.0,
                compensation_match_score=90.0,
                fits_criteria=True,
                recommendation=RecommendationType.QUEUE,
                rationale="Excellent match for Track A Embedded Leadership.",
                model_used="deterministic"
            )
            repo.save_evaluation(eval_mock)

            drafter = ApplicationGenerator(config=test_config, tenant=self.tenant)
            packages = drafter.draft_queued_jobs(job_id=saved_job.id)

            self.assertEqual(len(packages), 1)
            pkg = packages[0]
            self.assertTrue(Path(pkg.resume_md_path).exists())
            self.assertTrue(Path(pkg.resume_pdf_path).exists())
            self.assertTrue(Path(pkg.cover_letter_md_path).exists())
            self.assertTrue(Path(pkg.cover_letter_pdf_path).exists())
            self.assertTrue(Path(pkg.linkedin_prompt_path).exists())

            # Verify Job_Details.md generated
            job_details_path = Path(pkg.resume_md_path).parent / "Job_Details.md"
            self.assertTrue(job_details_path.exists())
            details_content = job_details_path.read_text(encoding="utf-8")
            self.assertIn("approve", details_content)
            self.assertIn("reject", details_content)
            self.assertIn(saved_job.id[:8], details_content)

            # Verify Education section in Resume
            resume_content = Path(pkg.resume_md_path).read_text(encoding="utf-8")
            self.assertIn("## Education", resume_content)
            self.assertIn("Istanbul Technical University", resume_content)
            self.assertIn("Iowa State University", resume_content)

            # Verify Cover Letter content and Job URL
            cover_content = Path(pkg.cover_letter_md_path).read_text(encoding="utf-8")
            self.assertIn("**Job URL:**", cover_content)
            self.assertIn("15 years of professional engineering experience", cover_content)
            self.assertIn("ISO 26262 ASIL D", cover_content)

    def test_pdf_nbsp_and_entity_cleaning(self):
        from src.utils.pdf import clean_text_for_pdf, strip_markdown_inline
        raw = "### Team Leader &nbsp;|&nbsp; ECEMTAG"
        cleaned = clean_text_for_pdf(raw)
        stripped = strip_markdown_inline(cleaned[4:])
        self.assertEqual(stripped, "Team Leader | ECEMTAG")

    def test_dashboard_generation(self):
        from src.utils.dashboard import generate_inbox_dashboard
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_config = self.config.model_copy(deep=True)
            test_config.database.db_path = Path(tmp_dir) / "test_dash.db"
            test_config.engine.inbox_dir = Path(tmp_dir) / "inbox"
            test_config.engine.inbox_dir.mkdir(parents=True, exist_ok=True)

            repo = JobRepository(test_config.database.db_path)
            repo.register_or_update_tenant(
                tenant_id=self.tenant.tenant_id,
                name=self.tenant.name,
                email=self.tenant.email,
                config_path=str(self.config.multi_tenancy.tenants_dir / self.tenant.tenant_id / "profile.yaml")
            )

            html_path = generate_inbox_dashboard(config=test_config, tenant=self.tenant)
            self.assertTrue(html_path.exists())
            html_text = html_path.read_text(encoding="utf-8")
            self.assertIn("Career Engine Review Dashboard", html_text)
            self.assertIn(self.tenant.name, html_text)
            self.assertIn("run.py approve", html_text)


if __name__ == "__main__":
    unittest.main()
