"""Unit tests for Phase 3 Sourcing Modules & Ingestion Pipeline."""

import sys
from pathlib import Path
import unittest
import tempfile

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from src.config import load_engine_config, load_tenant_profile
from src.database.models import TrackType
from src.database.repository import JobRepository
from src.sourcing.google_jobs import GoogleJobsScraper
from src.sourcing.apify_linkedin import ApifyLinkedInScraper
from src.sourcing.defense.baykar import BaykarScraper
from src.sourcing.defense.aselsan import AselsanScraper
from src.sourcing.defense.vizyoner_genc import VizyonerGencScraper
from src.sourcing.defense.tusas_roketsan import TusasScraper, RoketsanScraper
from src.sourcing.manager import SourcingManager


from unittest.mock import patch


class TestSourcing(unittest.TestCase):
    def setUp(self):
        self.config = load_engine_config()
        self.tenant = load_tenant_profile(config=self.config)

    def test_google_jobs_scraper(self):
        scraper = GoogleJobsScraper(self.config.sourcing, self.tenant)
        with patch.object(scraper, "fetch_raw_listings", return_value=scraper._get_mock_listings()):
            jobs = scraper.run()
            self.assertGreater(len(jobs), 0)
            for j in jobs:
                self.assertEqual(j.source, "google_jobs")
                self.assertTrue(len(j.deduplication_hash) == 64)
                self.assertIn(j.assigned_track, [TrackType.TRACK_A, TrackType.TRACK_B])

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
                self.assertEqual(j.company, "Baykar")
                self.assertEqual(j.assigned_track, TrackType.TRACK_A)

    def test_aselsan_scraper(self):
        scraper = AselsanScraper(self.config.sourcing, self.tenant)
        with patch.object(scraper, "fetch_raw_listings", return_value=scraper._get_mock_listings()):
            jobs = scraper.run()
            self.assertGreater(len(jobs), 0)
            for j in jobs:
                self.assertEqual(j.company, "ASELSAN")
                self.assertEqual(j.assigned_track, TrackType.TRACK_A)

    def test_vizyoner_genc_scraper(self):
        scraper = VizyonerGencScraper(self.config.sourcing, self.tenant)
        with patch.object(scraper, "fetch_raw_listings", return_value=scraper._get_mock_listings()):
            jobs = scraper.run()
            self.assertGreater(len(jobs), 0)
            for j in jobs:
                self.assertEqual(j.source, "vizyoner_genc")
                self.assertEqual(j.assigned_track, TrackType.TRACK_A)

    def test_tusas_scraper(self):
        scraper = TusasScraper(self.config.sourcing, self.tenant)
        jobs = scraper.run()
        self.assertGreater(len(jobs), 0)
        for j in jobs:
            self.assertEqual(j.source, "tusas")
            self.assertEqual(j.assigned_track, TrackType.TRACK_A)

    def test_roketsan_scraper(self):
        scraper = RoketsanScraper(self.config.sourcing, self.tenant)
        jobs = scraper.run()
        self.assertGreater(len(jobs), 0)
        for j in jobs:
            self.assertEqual(j.source, "roketsan")
            self.assertEqual(j.assigned_track, TrackType.TRACK_A)

    def test_sourcing_manager_orchestration(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_db = Path(tmp_dir) / "test_sourcing.db"
            test_config = self.config.model_copy(deep=True)
            test_config.database.db_path = temp_db

            manager = SourcingManager(config=test_config, tenant=self.tenant)
            
            mock_scrapers = []
            for scraper in manager.get_active_scrapers():
                if hasattr(scraper, "_get_mock_listings"):
                    scraper.fetch_raw_listings = scraper._get_mock_listings
                mock_scrapers.append(scraper)
            manager.get_active_scrapers = lambda name=None: mock_scrapers

            result = manager.run_sourcing_pipeline()

            self.assertGreater(result["total_discovered"], 0)
            self.assertEqual(result["new_jobs"], result["total_discovered"])

            # Second run must deduplicate all jobs (0 new)
            result_second = manager.run_sourcing_pipeline()
            self.assertEqual(result_second["new_jobs"], 0)
            self.assertEqual(result_second["existing_jobs"], result["total_discovered"])


if __name__ == "__main__":
    unittest.main()
