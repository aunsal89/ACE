"""Unit and integration tests for Telegram error handling, location compliance guardrails, dynamic sourcing mocks, and dashboard updates."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from src.config import EngineConfig, TenantManager, load_engine_config
from src.database.models import JobListing, JobListingCreate, JobStatus, RecommendationType
from src.database.repository import JobRepository
from src.scoring.llm_client import LLMScoringClient, OpportunityEvaluationSchema
from src.scoring.scorer import OpportunityScorer
from src.sourcing.apify_linkedin import ApifyLinkedInScraper
from src.sourcing.gmail_linkedin import GmailLinkedInScraper
from src.sourcing.google_jobs import GoogleJobsScraper
from src.utils.dashboard import generate_inbox_dashboard, normalize_position_group, normalize_region_group
from src.utils.hashing import generate_deduplication_hash
from src.utils.notifications import NotificationService


class TestDynamicScoringNotificationsDashboard(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)

        self.config = load_engine_config()
        self.config.multi_tenancy.tenants_dir = self.tmp_path / "tenants"
        self.config.engine.inbox_dir = self.tmp_path / "inbox"
        self.config.database.db_path = self.tmp_path / "test_eval.db"

        mgr = TenantManager(self.config)
        # Create a Control Systems / Mechanical Engineer profile in Istanbul
        self.tenant = mgr.create_tenant(
            tenant_id="control_engineer",
            name="Selin Yilmaz",
            email="selin@example.com",
            phone="+90 532 000 0000",
            location="Istanbul, Turkey",
            target_titles=["Control Systems Engineer", "Robotics Lead"],
            target_locations=["Istanbul, Turkey"],
            min_salary=6000.0,
            currency="USD",
        )
        self.tenant.preferences.core_competencies = [
            "MATLAB/Simulink",
            "Stateflow",
            "Nonlinear Control",
            "C/C++ Embedded",
        ]
        self.tenant.preferences.exclusions = ["Junior", "Intern", "Manual QA"]

    def tearDown(self):
        self.tmp_dir.cleanup()

    # --- 1. TELEGRAM ERROR HANDLING TESTS ---
    def test_telegram_chat_not_found_aborts_immediately(self):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123456:ABCDEF", "TELEGRAM_CHAT_ID": "99999999"}):
            notifier = NotificationService()
            mock_resp = MagicMock()
            mock_resp.status_code = 400
            mock_resp.json.return_value = {
                "ok": False,
                "error_code": 400,
                "description": "Bad Request: chat not found",
            }
            mock_resp.text = '{"ok":false,"error_code":400,"description":"Bad Request: chat not found"}'

            with patch("requests.post", return_value=mock_resp) as mock_post:
                ok = notifier.send_telegram("Test message", max_retries=3)
                self.assertFalse(ok)
                # Must abort immediately on chat not found without retries
                self.assertEqual(mock_post.call_count, 1)

    def test_telegram_entity_parsing_error_retries_plain_text(self):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123456:ABCDEF", "TELEGRAM_CHAT_ID": "99999999"}):
            notifier = NotificationService()
            # Attempt 1: 400 entity parse error
            mock_resp_entity_err = MagicMock()
            mock_resp_entity_err.status_code = 400
            mock_resp_entity_err.json.return_value = {
                "ok": False,
                "error_code": 400,
                "description": "Bad Request: can't parse entities: unclosed tag",
            }

            # Attempt 2: 200 Success with plain text
            mock_resp_ok = MagicMock()
            mock_resp_ok.status_code = 200
            mock_resp_ok.json.return_value = {"ok": True}

            with patch("requests.post", side_effect=[mock_resp_entity_err, mock_resp_ok]) as mock_post:
                ok = notifier.send_telegram("<b>Unclosed text", max_retries=3)
                self.assertTrue(ok)
                self.assertEqual(mock_post.call_count, 2)
                # Second call should have parse_mode omitted/None
                second_payload = mock_post.call_args_list[1][1]["json"]
                self.assertNotIn("parse_mode", second_payload)
                self.assertEqual(second_payload["text"], "Unclosed text")

    # --- 2. LOCATION COMPLIANCE & SCORING TESTS ---
    def test_location_mismatch_strictly_penalized_and_rejected(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        client = LLMScoringClient(settings=self.config.llm, tenant=self.tenant)

        # Job in London (Candidate target location is only Istanbul, Turkey)
        job_london = JobListing(
            id="job_lon_01",
            deduplication_hash="hash_lon_01",
            source="google_jobs",
            title="Senior Control Systems Engineer",
            company="DeepMotion Ltd",
            location="London, United Kingdom",
            is_remote=False,
            description_raw="Seeking Control Systems Engineer with MATLAB Simulink and C++ expertise.",
            status=JobStatus.DISCOVERED,
            discovered_at=now,
            updated_at=now,
        )

        eval_result = client.evaluate_fit(job_london)
        self.assertFalse(eval_result.fits_criteria)
        self.assertEqual(eval_result.recommendation, "REJECT")
        self.assertLessEqual(eval_result.location_score, 20.0)
        self.assertLessEqual(eval_result.overall_score, 45.0)
        self.assertIn("Location Mismatch", eval_result.reasoning)

    def test_location_match_in_target_city_qualifies(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        client = LLMScoringClient(settings=self.config.llm, tenant=self.tenant)

        # Job in Istanbul matching candidate preference
        job_istanbul = JobListing(
            id="job_ist_01",
            deduplication_hash="hash_ist_01",
            source="baykar",
            title="Control Systems & Robotics Lead",
            company="Baykar",
            location="Istanbul, Turkey",
            is_remote=False,
            description_raw="Leading flight control algorithms, MATLAB/Simulink, and nonlinear control systems.",
            status=JobStatus.DISCOVERED,
            discovered_at=now,
            updated_at=now,
        )

        eval_result = client.evaluate_fit(job_istanbul)
        self.assertTrue(eval_result.fits_criteria)
        self.assertEqual(eval_result.recommendation, "QUEUE")
        self.assertEqual(eval_result.location_score, 100.0)
        self.assertGreaterEqual(eval_result.overall_score, 75.0)

    # --- 3. DYNAMIC SOURCING MOCKS TESTS ---
    def test_scrapers_dynamic_mock_generation_matches_candidate_profile(self):
        gj_scraper = GoogleJobsScraper(self.config.sourcing, self.tenant)
        mock_gj = gj_scraper._get_mock_listings()

        self.assertGreaterEqual(len(mock_gj), 1)
        # Should NOT contain hardcoded quantitative trading jobs
        for m in mock_gj:
            self.assertNotIn("Quantitative Software Engineer", m["title"])
            self.assertNotIn("Man Group", m["company_name"])
            self.assertIn(m["location"], self.tenant.preferences.target_locations or ["Remote"])

        li_scraper = ApifyLinkedInScraper(self.config.sourcing, self.tenant)
        mock_li = li_scraper._get_mock_listings()
        for m in mock_li:
            self.assertNotIn("Wintermute", m["companyName"])

        gmail_scraper = GmailLinkedInScraper(self.config.sourcing, self.tenant)
        mock_gmail = gmail_scraper._get_mock_listings()
        for m in mock_gmail:
            self.assertNotIn("Rheinmetall", m["company"])

    # --- 4. DASHBOARD GENERATION & FILTER TESTS ---
    def test_dashboard_generation_without_legacy_tracks(self):
        repo = JobRepository(self.config.database.db_path)
        repo.register_or_update_tenant(
            tenant_id=self.tenant.tenant_id,
            name=self.tenant.name,
            email=self.tenant.email,
            config_path=str(self.config.multi_tenancy.tenants_dir / self.tenant.tenant_id / "profile.yaml"),
        )

        # Ingest a sample job
        job_in = JobListingCreate(
            deduplication_hash=generate_deduplication_hash("Baykar", "Control Systems Engineer", "Istanbul"),
            source="baykar",
            title="Lead Control Systems Engineer",
            company="Baykar",
            location="Istanbul, Turkey",
            description_raw="Flight control and robotics engineering.",
            assigned_track="GENERAL",
            status=JobStatus.QUEUED,
        )
        saved_job, _ = repo.upsert_job(job_in)

        # Generate dashboard
        dash_path = generate_inbox_dashboard(config=self.config, tenant=self.tenant)
        self.assertTrue(dash_path.exists())

        html_text = dash_path.read_text(encoding="utf-8")
        # Verify legacy Track A (Embedded) / Track B (Quant) pills are completely absent
        self.assertNotIn("All Tracks", html_text)
        self.assertNotIn("Track A (Embedded)", html_text)
        self.assertNotIn("Track B (Quant)", html_text)
        self.assertNotIn("badge-track-a", html_text)
        self.assertNotIn("badge-track-b", html_text)

        # Verify dynamic Fit Score Breakdown donut and Status/Score filters are present
        self.assertIn("Fit Score Breakdown", html_text)
        self.assertIn("High Fit (80%+)", html_text)
        self.assertIn("scoreFilterPills", html_text)
        self.assertIn("workplaceFilterPills", html_text)
        self.assertIn(self.tenant.name, html_text)

    # --- 5. SCORER PYDANTIC SCHEMA & QUERY TESTS ---
    def test_scorer_evaluate_pydantic_schema_compatibility(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        scorer = OpportunityScorer(config=self.config, tenant=self.tenant)

        job = JobListing(
            id="job_pydantic_01",
            deduplication_hash="hash_pydantic_01",
            source="test_source",
            title="Senior Robotics Engineer",
            company="Test Robotics Inc",
            location="Istanbul, Turkey",
            is_remote=False,
            description_raw="Control and robotics engineering.",
            status=JobStatus.DISCOVERED,
            discovered_at=now,
            updated_at=now,
        )

        mock_schema = OpportunityEvaluationSchema(
            overall_score=88.5,
            comp_score=90.0,
            location_score=100.0,
            tech_stack_score=85.0,
            leadership_score=80.0,
            fits_criteria=True,
            reasoning="Strong technical alignment.",
            matched_keywords=["Robotics", "Control"],
            missing_keywords=[],
            recommendation="QUEUE",
            model_used="test_model",
            track="GENERAL",
        )

        with patch.object(scorer.llm_client, "evaluate_fit", return_value=mock_schema):
            eval_create = scorer.evaluate(job)
            self.assertEqual(eval_create.overall_score, 88.5)
            self.assertEqual(eval_create.recommendation, RecommendationType.QUEUE)
            self.assertEqual(eval_create.track, "GENERAL")
            self.assertEqual(eval_create.location_score, 100.0)

    def test_serpapi_query_building(self):
        gj_scraper = GoogleJobsScraper(self.config.sourcing, self.tenant)
        queries = gj_scraper.build_search_queries()
        self.assertGreaterEqual(len(queries), 1)
        for q_spec in queries:
            self.assertIn("q", q_spec)
            self.assertTrue(len(q_spec["q"]) > 0)
            # Location should be embedded cleanly into the query string
            self.assertIn("Istanbul", q_spec["q"])


if __name__ == "__main__":
    unittest.main()

