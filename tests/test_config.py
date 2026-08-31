"""Unit tests for Autonomous Career Engine configuration and dynamic tenant provisioning."""

import sys
from pathlib import Path
import unittest
import tempfile
import yaml

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from src.config import EngineConfig, load_engine_config, load_tenant_profile, TenantManager, PROJECT_ROOT


class TestConfig(unittest.TestCase):
    def test_load_engine_config_defaults(self):
        config = load_engine_config()
        self.assertEqual(config.engine.name, "Autonomous Career Engine")
        self.assertTrue(config.database.wal_mode)
        self.assertTrue(isinstance(config.database.db_path, Path))
        self.assertTrue(isinstance(config.engine.inbox_dir, Path))
        self.assertFalse("/home/nsl/Portfolio" in str(config.database.db_path))

    def test_dynamic_tenant_creation_and_management(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_config = load_engine_config().model_copy(deep=True)
            test_config.multi_tenancy.tenants_dir = Path(tmp_dir) / "tenants"
            test_config.engine.inbox_dir = Path(tmp_dir) / "inbox"

            mgr = TenantManager(test_config)
            self.assertEqual(len(mgr.list_available_tenants()), 0)

            # Create new candidate tenant dynamically
            tenant = mgr.create_tenant(
                tenant_id="jane_doe",
                name="Jane Doe",
                email="jane.doe@example.com",
                phone="+1-555-0100",
                location="San Francisco, CA",
                target_titles=["Lead Systems Engineer", "Engineering Director"],
                target_locations=["San Francisco, CA", "Remote"],
                min_salary=8500.0,
                currency="USD"
            )

            self.assertEqual(tenant.tenant_id, "jane_doe")
            self.assertEqual(tenant.name, "Jane Doe")
            self.assertEqual(tenant.email, "jane.doe@example.com")
            self.assertEqual(tenant.tracks.track_a.compensation.min_monthly_net_usd, 8500.0)
            self.assertIn("Lead Systems Engineer", tenant.tracks.track_a.target_titles)

            # Check listing
            tenants = mgr.list_available_tenants()
            self.assertIn("jane_doe", tenants)

            # Check loading
            loaded = mgr.get_tenant("jane_doe")
            self.assertEqual(loaded.name, "Jane Doe")


if __name__ == "__main__":
    unittest.main()
