import sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

"""Unit tests for Career Engine configuration and tenant profiles."""

import unittest
from pathlib import Path
from src.config import load_engine_config, load_tenant_profile, TenantManager


class TestConfig(unittest.TestCase):
    def test_load_engine_config(self):
        config = load_engine_config()
        self.assertEqual(config.engine.name, "Career Engine")
        self.assertTrue(config.database.wal_mode)
        self.assertEqual(config.multi_tenancy.active_tenant, "aunsal")

    def test_load_tenant_profile_aunsal(self):
        tenant = load_tenant_profile("aunsal")
        self.assertEqual(tenant.tenant_id, "aunsal")
        self.assertEqual(tenant.name, "Ahmet Halit Ünsal")
        self.assertTrue(tenant.tracks.track_a.enabled)
        self.assertTrue(tenant.tracks.track_b.enabled)
        self.assertEqual(tenant.tracks.track_a.compensation.min_monthly_net_usd, 8600.0)
        self.assertIn("United States", tenant.tracks.track_b.excluded_regions)
        self.assertIn("Model-Based Design (MBD)", tenant.tracks.track_a.core_competencies)

    def test_tenant_manager(self):
        mgr = TenantManager()
        tenants = mgr.list_available_tenants()
        self.assertIn("aunsal", tenants)
        tenant = mgr.get_tenant("aunsal")
        self.assertEqual(tenant.name, "Ahmet Halit Ünsal")


if __name__ == "__main__":
    unittest.main()
