from __future__ import annotations

from tests.base import TempDBTestCase
from utils.feature_flags import FeatureFlagService


class FeatureFlagTests(TempDBTestCase):
    def test_defaults_are_available(self):
        svc = FeatureFlagService(self.db, "user-a")
        svc.ensure_defaults()

        self.assertTrue(svc.is_enabled("in_app_notifications"))
        self.assertTrue(svc.is_enabled("enhanced_recipe_search"))

    def test_user_override_beats_global(self):
        svc = FeatureFlagService(self.db, "user-a")
        svc.ensure_defaults()
        svc.set_global("enhanced_recipe_search", False)
        svc.set_user("enhanced_recipe_search", True)

        self.assertTrue(svc.is_enabled("enhanced_recipe_search"))

    def test_remote_cache_used_when_present(self):
        svc = FeatureFlagService(self.db, "user-a")
        self.db.set_setting(
            "ff.remote.global.enhanced_recipe_search",
            '{"enabled": false, "rollout_pct": 100}',
        )

        self.assertFalse(svc.is_enabled("enhanced_recipe_search", default=True))


if __name__ == "__main__":
    import unittest

    unittest.main()
