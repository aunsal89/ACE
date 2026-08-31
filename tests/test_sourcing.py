"""Unit tests for Sourcing Modules & Ingestion Pipeline."""

import sys
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from src.config import load_engine_config, TenantManager
from src.database.models import TrackType
from src.database.repository import JobRepository
from src.sourcing.google_jobs import GoogleJobsScraper
from src.sourcing.gmail_linkedin import GmailLinkedInScraper
from src.sourcing.apify_linkedin import ApifyLinkedInScraper
from src.sourcing.defense.baykar import BaykarScraper
from src.sourcing.defense.aselsan import AselsanScraper
from src.sourcing.defense.vizyoner_genc import VizyonerGencScraper
from src.sourcing.defense.tusas_roketsan import TusasScraper, RoketsanScraper
from src.sourcing.manager import SourcingManager


class TestSourcing(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        
        self.config = load_engine_config()
        self.config.multi_tenancy.tenants_dir = self.tmp_path / "tenants"
        self.config.engine.inbox_dir = self.tmp_path / "inbox"
        self.config.database.db_path = self.tmp_path / "test_sourcing.db"

        mgr = TenantManager(self.config)
        self.tenant = mgr.create_tenant(
            tenant_id="test_candidate",
            name="Test Candidate",
            email="candidate@example.com",
            location="Ankara, Turkey",
            target_titles=["Embedded Software Lead", "Quant Developer"],
            target_locations=["Ankara, Turkey", "Istanbul, Turkey", "London"],
            min_salary=8000.0
        )
        self.tenant.tracks.track_b.enabled = True
        self.tenant.tracks.track_b.target_titles = ["Quant Developer"]

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_google_jobs_scraper(self):
        scraper = GoogleJobsScraper(self.config.sourcing, self.tenant)
        with patch.object(scraper, "fetch_raw_listings", return_value=scraper._get_mock_listings()):
            jobs = scraper.run()
            self.assertGreater(len(jobs), 0)
            for j in jobs:
                self.assertEqual(j.source, "google_jobs")
                self.assertTrue(len(j.deduplication_hash) == 64)
                self.assertIn(j.assigned_track, [TrackType.TRACK_A, TrackType.TRACK_B])

    def test_gmail_linkedin_scraper(self):
        scraper = GmailLinkedInScraper(self.config.sourcing, self.tenant, imap_user="mock@gmail.com", imap_password="mock_password")
        with patch.object(scraper, "fetch_raw_listings", return_value=scraper._get_mock_listings()):
            jobs = scraper.run()
            self.assertEqual(len(jobs), 2)
            for j in jobs:
                self.assertEqual(j.source, "gmail_linkedin")
                self.assertTrue(len(j.deduplication_hash) == 64)
                self.assertEqual(j.assigned_track, TrackType.TRACK_A)

    def test_apify_linkedin_scraper(self):
        scraper = ApifyLinkedInScraper(self.config.sourcing, self.tenant)
        with patch.object(scraper, "fetch_raw_listings", return_value=scraper._get_mock_listings()):
            jobs = scraper.run()
            self.assertGreater(len(jobs), 0)
            for j in jobs:
                self.assertEqual(j.source, "apify_linkedin")
                self.assertIn(j.assigned_track, [TrackType.TRACK_A, TrackType.TRACK_B])

    def test_baykar_scraper(self):
        scraper = BaykarScraper(self.config.sourcing, self.tenant)
        with patch.object(scraper, "fetch_raw_listings", return_value=scraper._get_mock_listings()):
            jobs = scraper.run()
            self.assertGreater(len(jobs), 0)
            for j in jobs:
                self.assertEqual(j.source, "baykar")
                self.assertEqual(j.company, "Baykar")

    def test_aselsan_scraper(self):
        scraper = AselsanScraper(self.config.sourcing, self.tenant)
        with patch.object(scraper, "fetch_raw_listings", return_value=scraper._get_mock_listings()):
            jobs = scraper.run()
            self.assertGreater(len(jobs), 0)
            for j in jobs:
                self.assertEqual(j.source, "aselsan")
                self.assertEqual(j.company, "ASELSAN")

    def test_vizyoner_genc_scraper(self):
        scraper = VizyonerGencScraper(self.config.sourcing, self.tenant)
        with patch.object(scraper, "fetch_raw_listings", return_value=scraper._get_mock_listings()):
            jobs = scraper.run()
            self.assertGreater(len(jobs), 0)
            for j in jobs:
                self.assertEqual(j.source, "vizyoner_genc")

    def test_tusas_and_roketsan_scrapers(self):
        tusas = TusasScraper(self.config.sourcing, self.tenant)
        roketsan = RoketsanScraper(self.config.sourcing, self.tenant)

        t_jobs = tusas.run()
        self.assertGreater(len(t_jobs), 0)
        self.assertEqual(t_jobs[0].source, "tusas")

        r_jobs = roketsan.run()
        self.assertGreater(len(r_jobs), 0)
        self.assertEqual(r_jobs[0].source, "roketsan")

    def test_sourcing_manager_orchestration(self):
        manager = SourcingManager(config=self.config, tenant=self.tenant)
        repo = JobRepository(self.config.database.db_path)
        repo.register_or_update_tenant(
            tenant_id=self.tenant.tenant_id,
            name=self.tenant.name,
            email=self.tenant.email,
            config_path=str(self.config.multi_tenancy.tenants_dir / self.tenant.tenant_id / "profile.yaml")
        )

        res = manager.run_sourcing_pipeline(dry_run=True)
        self.assertIn("total_discovered", res)
        self.assertGreater(res["total_discovered"], 0)


if __name__ == "__main__":
    unittest.main()
