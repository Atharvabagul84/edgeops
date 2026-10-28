import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.device_agent import Outbox, send_events


class DeviceAgentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "agent.sqlite3"

    def tearDown(self):
        self.directory.cleanup()

    def test_offline_readings_survive_restart_with_increasing_sequences(self):
        with Outbox(self.path, "edge-003") as first:
            a = first.sample(42)
        with Outbox(self.path, "edge-003") as second:
            b = second.sample(43)
            self.assertEqual(second.pending_count(), 2)
            self.assertGreater(b["sequence"], a["sequence"])
            self.assertNotEqual(a["eventId"], b["eventId"])

    def test_failed_network_delivery_preserves_every_reading(self):
        with Outbox(self.path, "edge-003") as outbox:
            outbox.sample(42)
            outbox.sample(43)
            def fail(events):
                raise OSError("network unavailable")
            with self.assertRaises(OSError):
                outbox.flush(fail)
            self.assertEqual(outbox.pending_count(), 2)

    def test_only_successfully_acknowledged_batches_leave_outbox(self):
        batches = []
        with Outbox(self.path, "edge-003") as outbox:
            first = outbox.sample(42)
            second = outbox.sample(43)
            delivered = outbox.flush(lambda events: batches.append(events), batch_size=1)
            self.assertEqual(delivered, 2)
            self.assertEqual(outbox.pending_count(), 0)
            self.assertEqual(batches, [[first], [second]])
            self.assertEqual(outbox.last_delivered(), second)

    def test_partial_failure_keeps_unsent_batch_for_later(self):
        calls = []
        with Outbox(self.path, "edge-003") as outbox:
            outbox.sample(42)
            last = outbox.sample(43)
            def sometimes(events):
                calls.append(events)
                if len(calls) == 2:
                    raise OSError("connection dropped")
            with self.assertRaises(OSError):
                outbox.flush(sometimes, batch_size=1)
            self.assertEqual(outbox.pending_count(), 1)
            retried = []
            outbox.flush(lambda events: retried.extend(events))
            self.assertEqual(retried, [last])

    def test_remote_plain_http_url_is_rejected_before_credentials_can_be_sent(self):
        with patch('scripts.device_agent._http.open', side_effect=AssertionError('Must reject before opening network')), self.assertRaises(ValueError):
            send_events("http://aws-demo.example", [])


if __name__ == "__main__":
    unittest.main()
