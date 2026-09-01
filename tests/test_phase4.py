"""Unit tests for Phase 4: Scoring Engine, PDF Rendering & Application Drafting."""

import sys
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from src.config import EngineConfig, load_engine_config, TenantManager
from src.database.models import JobListingCreate, JobStatus, RecommendationType
from src.database.repository import JobRepository
from src.scoring.scorer import OpportunityScorer
from src.applicator.generator import ApplicationGenerator
from src.utils.hashing import generate_deduplication_hash
from src.utils.pdf import render_markdown_to_pdf


class TestPhase4(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        
        self.config = load_engine_config()
        self.config.multi_tenancy.tenants_dir = self.tmp_path / "tenants"
        self.config.engine.inbox_dir = self.tmp_path / "inbox"
        self.config.database.db_path = self.tmp_path / "test_phase4.db"

        mgr = TenantManager(self.config)
        self.tenant = mgr.create_tenant(
            tenant_id="test_candidate",
            name="Test Candidate",
            email="candidate@example.com",
            phone="+1 (555) 0199",
            location="Ankara, Turkey",
            target_titles=["Embedded Software Director", "Quant Developer"],
            target_locations=["Ankara, Turkey", "London"],
            min_salary=8000.0,
            currency="USD"
        )
        # Enable track B as well for testing
        self.tenant.tracks.track_b.enabled = True
        self.tenant.tracks.track_b.target_titles = ["Quant Developer"]
        self.tenant.tracks.track_b.core_competencies = ["Python", "C++", "CCXT", "pandas"]

        # Populate sample CV markdown sources
        sources_dir = self.config.multi_tenancy.tenants_dir / "test_candidate" / "sources"
        sources_dir.mkdir(parents=True, exist_ok=True)
        (sources_dir / "Experience.md").write_text(
            "# Professional Experience\n\n15+ years experience leading Model-Based Design and ISO 26262 ASIL D systems.",
            encoding="utf-8"
        )
        (sources_dir / "Education.md").write_text(
            "# Education\n\n**MSc Computer Science** | ITU | 2016\n**BSc Electrical Engineering** | ISU | 2011",
            encoding="utf-8"
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_pdf_renderer(self):
        pdf_path = self.tmp_path / "test_cv.pdf"
        sample_md = """# Test Candidate
## Embedded Software Director

* **Model-Based Design:** 15+ years experience in MATLAB/Simulink.
* **ISO 26262:** ASIL D functional safety leadership.
"""
        out = render_markdown_to_pdf(sample_md, pdf_path, doc_title="Test Document")
        self.assertTrue(out.exists())
        self.assertGreater(out.stat().st_size, 500)

    def test_scoring_engine_opportunity_evaluation(self):
        scorer = OpportunityScorer(config=self.config, tenant=self.tenant)
        job = JobListingCreate(
            deduplication_hash=generate_deduplication_hash("ASELSAN", "Embedded Software Director", "Ankara"),
            source="aselsan",
            title="Embedded Software Director (MBD / Powertrain)",
            company="ASELSAN",
            location="Ankara, Turkey",
            description_raw="Leading 30 engineers in Model-Based Design, Simulink, AUTOSAR, and ISO 26262 ASIL D.",
            assigned_track="GENERAL",
            status=JobStatus.DISCOVERED
        )
        repo = JobRepository(self.config.database.db_path)
        repo.register_or_update_tenant(
            tenant_id=self.tenant.tenant_id,
            name=self.tenant.name,
            email=self.tenant.email,
            config_path=str(self.config.multi_tenancy.tenants_dir / self.tenant.tenant_id / "profile.yaml")
        )
        saved_job, _ = repo.upsert_job(job)

        with patch.object(scorer.llm_client, "evaluate_fit", side_effect=scorer.llm_client._evaluate_deterministic):
            evaluation = scorer.evaluate(saved_job)
            self.assertEqual(evaluation.track, "GENERAL")
            self.assertGreaterEqual(evaluation.overall_score, 75.0)
            self.assertEqual(evaluation.recommendation, RecommendationType.QUEUE)
            self.assertTrue(evaluation.fits_criteria)

    def test_application_generator(self):
        repo = JobRepository(self.config.database.db_path)
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
            assigned_track="GENERAL",
            status=JobStatus.QUEUED
        )
        saved_job, _ = repo.upsert_job(job)

        from src.database.models import ScoringEvaluationCreate
        eval_mock = ScoringEvaluationCreate(
            job_id=saved_job.id,
            tenant_id=self.tenant.tenant_id,
            track="GENERAL",
            overall_score=92.0,
            fits_criteria=True,
            recommendation=RecommendationType.QUEUE,
            reasoning="Excellent match for Candidate Profile.",
            model_used="deterministic"
        )
        repo.save_evaluation(eval_mock)

        drafter = ApplicationGenerator(config=self.config, tenant=self.tenant)
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

        # Verify Cover Letter content and Job URL
        cover_content = Path(pkg.cover_letter_md_path).read_text(encoding="utf-8")
        self.assertIn("**Job URL:**", cover_content)

    def test_pdf_nbsp_and_entity_cleaning(self):
        from src.utils.pdf import clean_text_for_pdf, strip_markdown_inline
        raw = "### Team Leader &nbsp;|&nbsp; ECEMTAG"
        cleaned = clean_text_for_pdf(raw)
        stripped = strip_markdown_inline(cleaned[4:])
        self.assertEqual(stripped, "Team Leader | ECEMTAG")

    def test_dashboard_generation(self):
        from src.utils.dashboard import generate_inbox_dashboard
        repo = JobRepository(self.config.database.db_path)
        repo.register_or_update_tenant(
            tenant_id=self.tenant.tenant_id,
            name=self.tenant.name,
            email=self.tenant.email,
            config_path=str(self.config.multi_tenancy.tenants_dir / self.tenant.tenant_id / "profile.yaml")
        )

        html_path = generate_inbox_dashboard(config=self.config, tenant=self.tenant)
        self.assertTrue(html_path.exists())
        html_text = html_path.read_text(encoding="utf-8")
        self.assertIn("Review Dashboard", html_text)
        self.assertIn(self.tenant.name, html_text)


if __name__ == "__main__":
    unittest.main()
