"""Unit tests for Target Companies Configuration, CLI, and Targeted Sourcing."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from src.config import (
    EngineConfig,
    TargetCompanyConfig,
    TenantManager,
    load_engine_config,
    load_tenant_profile,
)
from src.sourcing.targeted_companies import TargetedCompanyScraper
from src.utils.dashboard import generate_inbox_dashboard


class TestTargetCompanies(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)

        self.config = load_engine_config()
        self.config.multi_tenancy.tenants_dir = self.tmp_path / "tenants"
        self.config.engine.inbox_dir = self.tmp_path / "inbox"
        self.config.database.db_path = self.tmp_path / "test_target_companies.db"

        self.mgr = TenantManager(self.config)
        self.tenant = self.mgr.create_tenant(
            tenant_id="test_engineer",
            name="Test Engineer",
            email="engineer@example.com",
            location="Amsterdam, Netherlands",
            target_titles=["Lead Systems Architect", "Principal Software Engineer"],
            target_locations=["Amsterdam", "Remote"],
            min_salary=9000.0,
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_target_company_config_validation(self):
        comp = TargetCompanyConfig(
            name="ASML",
            url="https://www.asml.com/en/careers",
            location="Veldhoven, Netherlands",
            enabled=True,
            keywords=["Semiconductor", "Robotics"],
        )
        self.assertEqual(comp.name, "ASML")
        self.assertEqual(comp.url, "https://www.asml.com/en/careers")
        self.assertTrue(comp.enabled)
        self.assertIn("Semiconductor", comp.keywords)

    def test_tenant_manager_company_crud(self):
        # 1. Fallback / initial loading
        initial_comps = self.mgr.load_target_companies(self.tenant.tenant_id)
        self.assertIsInstance(initial_comps, list)

        # 2. Add custom company
        added = self.mgr.add_target_company(
            tenant_id=self.tenant.tenant_id,
            name="Custom Semiconductor Corp",
            url="https://careers.customsemi.example",
            location="Eindhoven, Netherlands",
            keywords=["Lithography", "C++"],
        )
        self.assertEqual(added.name, "Custom Semiconductor Corp")

        # 3. Verify persistence in tenant-specific file
        target_file = self.config.multi_tenancy.tenants_dir / self.tenant.tenant_id / "target_companies.yaml"
        self.assertTrue(target_file.exists())

        loaded = self.mgr.load_target_companies(self.tenant.tenant_id)
        names = [c.name for c in loaded]
        self.assertIn("Custom Semiconductor Corp", names)

        # 4. Remove company
        removed = self.mgr.remove_target_company(self.tenant.tenant_id, "Custom Semiconductor Corp")
        self.assertTrue(removed)

        loaded_after = self.mgr.load_target_companies(self.tenant.tenant_id)
        names_after = [c.name for c in loaded_after]
        self.assertNotIn("Custom Semiconductor Corp", names_after)

    def test_targeted_company_scraper(self):
        # Add target company to tenant
        self.mgr.add_target_company(
            tenant_id=self.tenant.tenant_id,
            name="ASML",
            url="https://www.asml.com/en/careers",
            location="Veldhoven, Netherlands",
        )
        tenant_refreshed = self.mgr.get_tenant(self.tenant.tenant_id)
        scraper = TargetedCompanyScraper(self.config.sourcing, tenant_refreshed)

        # Test scraper run
        jobs = scraper.run()
        self.assertGreater(len(jobs), 0)
        for j in jobs:
            self.assertEqual(j.source, "targeted_companies")
            self.assertTrue(j.url.startswith(("http://", "https://")))
            self.assertTrue(len(j.deduplication_hash) == 64)

    def test_multi_tenant_dashboard_isolation(self):
        # Generate dashboard
        dash_path = generate_inbox_dashboard(config=self.config, tenant=self.tenant)
        self.assertTrue(dash_path.exists())

        # Check tenant-specific inbox location: inbox/<tenant_id>/index.html
        expected_tenant_path = self.config.engine.inbox_dir / self.tenant.tenant_id / "index.html"
        self.assertEqual(dash_path.resolve(), expected_tenant_path.resolve())

        # Check top-level inbox/index.html mirror
        top_level_dash = self.config.engine.inbox_dir / "index.html"
        self.assertTrue(top_level_dash.exists())

        content = dash_path.read_text(encoding="utf-8")
        self.assertIn("Test Engineer", content)


if __name__ == "__main__":
    unittest.main()
