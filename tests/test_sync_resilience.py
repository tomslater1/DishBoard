from __future__ import annotations

import unittest

from utils.sync_resilience import SyncResilienceController


class SyncResilienceControllerTests(unittest.TestCase):
    def test_backoff_and_circuit_progression(self):
        ctl = SyncResilienceController(
            min_backoff_seconds=2,
            max_backoff_seconds=10,
            circuit_after_failures=3,
            circuit_open_seconds=20,
        )

        ok, retry, reason = ctl.can_attempt(now=0)
        self.assertTrue(ok)
        self.assertEqual(retry, 0)
        self.assertEqual(reason, "ready")

        s1 = ctl.record_failure("first", now=10)
        self.assertEqual(s1["reason"], "backoff")
        self.assertEqual(s1["retry_in_seconds"], 2)

        ok2, retry2, reason2 = ctl.can_attempt(now=11)
        self.assertFalse(ok2)
        self.assertEqual(reason2, "backoff")
        self.assertEqual(retry2, 1)

        s2 = ctl.record_failure("second", now=20)
        self.assertEqual(s2["reason"], "backoff")
        self.assertEqual(s2["retry_in_seconds"], 4)

        s3 = ctl.record_failure("third", now=30)
        self.assertEqual(s3["reason"], "circuit_open")
        self.assertEqual(s3["retry_in_seconds"], 20)

        ok3, retry3, reason3 = ctl.can_attempt(now=40)
        self.assertFalse(ok3)
        self.assertEqual(reason3, "circuit_open")
        self.assertEqual(retry3, 10)

        ok4, _, _ = ctl.can_attempt(now=51)
        self.assertTrue(ok4)

    def test_success_resets_failure_state(self):
        ctl = SyncResilienceController(min_backoff_seconds=1, circuit_after_failures=4)
        ctl.record_failure("boom", now=5)
        ctl.record_failure("boom2", now=7)
        self.assertGreater(ctl.status(now=7)["consecutive_failures"], 0)

        ctl.record_success()
        status = ctl.status(now=8)
        self.assertEqual(status["consecutive_failures"], 0)
        self.assertFalse(status["circuit_open"])
        self.assertEqual(status["retry_in_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
