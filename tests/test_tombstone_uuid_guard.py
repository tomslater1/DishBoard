from __future__ import annotations

from auth.cloud_sync import CloudSyncService, _is_uuid
from tests.base import TempDBTestCase


class _FakeInsert:
    def __init__(self, sink: list[dict], payload: dict):
        self._sink = sink
        self._payload = payload

    def execute(self):
        self._sink.append(self._payload)
        return type("Res", (), {"data": [self._payload]})()


class _FakeTable:
    def __init__(self, sink: list[dict]):
        self._sink = sink

    def insert(self, payload: dict):
        return _FakeInsert(self._sink, payload)


class _FakeClient:
    def __init__(self):
        self.inserted: list[dict] = []

    def table(self, _name: str):
        return _FakeTable(self.inserted)


class TombstoneUUIDGuardTests(TempDBTestCase):
    def test_is_uuid_helper(self):
        self.assertTrue(_is_uuid("550e8400-e29b-41d4-a716-446655440000"))
        self.assertFalse(_is_uuid("53"))

    def test_push_tombstones_drops_non_uuid_legacy_ids(self):
        valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
        self.db.add_tombstone("recipes", "53")
        self.db.add_tombstone("recipes", valid_uuid)

        fake_client = _FakeClient()
        svc = CloudSyncService("user-123")
        svc._push_tombstones(self.db, fake_client)

        pending = self.db.get_pending_tombstones()
        self.assertEqual(pending, [])
        self.assertEqual(len(fake_client.inserted), 1)
        self.assertEqual(fake_client.inserted[0]["cloud_id"], valid_uuid)


if __name__ == "__main__":
    import unittest

    unittest.main()
