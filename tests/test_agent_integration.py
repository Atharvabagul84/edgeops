import json
import io
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from backend.server import create_server
from scripts.device_agent import Outbox, main, send_events


class AgentIntegrationTests(unittest.TestCase):
    def test_separate_durable_outbox_replays_over_real_http_without_double_counting(self):
        with tempfile.TemporaryDirectory() as directory:
            server = create_server(Path(directory) / "fleet.sqlite3", port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with urlopen(base + "/api/state") as response:
                    before = json.load(response)
                spool = Path(directory) / "edge.sqlite3"
                with Outbox(spool, "edge-003") as offline:
                    for temperature in (41, 42, 43):
                        offline.sample(temperature)
                with urlopen(base + "/api/state") as response:
                    self.assertEqual(json.load(response)["stats"]["ingested"], before["stats"]["ingested"])
                with Outbox(spool, "edge-003") as connected:
                    self.assertEqual(connected.pending_count(), 3)
                    self.assertEqual(connected.flush(lambda batch: send_events(base, batch)), 3)
                    self.assertEqual(connected.pending_count(), 0)
                    after = send_events(base, [connected.last_delivered()])
                self.assertEqual(after["stats"]["ingested"], before["stats"]["ingested"] + 3)
                self.assertEqual(after["stats"]["duplicates"], before["stats"]["duplicates"] + 1)
                self.assertEqual(after["delivery"]["stage"], "processed-or-deduplicated")
                self.assertEqual(after["delivery"]["httpStatus"], 200)
                self.assertEqual(next(device for device in after["devices"] if device["id"] == "edge-003")["temperature"], 43)
                with urlopen(base + "/api/export") as response:
                    export = json.load(response)
                self.assertTrue(export["demo"])
                self.assertIn("Synthetic", export["diagnosticNote"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


class QueueAcknowledgementTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.payload = {"accepted": 2, "messageId": "queue-message-123"}
        self.status = 202
        self.requests = []
        fixture = self

        class QueueServer(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fixture.requests.append({"path": self.path, "authorization": self.headers.get("Authorization"), "body": body})
                payload = json.dumps(fixture.payload).encode()
                self.send_response(fixture.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                if fixture.status == 302:
                    self.send_header("Location", fixture.base + '/redirected')
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                fixture.requests.append({"path": self.path, "authorization": self.headers.get("Authorization")})
                payload = json.dumps({"stats": {"ingested": 1}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), QueueServer)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.spool = Path(self.directory.name) / "edge.sqlite3"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.directory.cleanup()

    def test_202_transfers_outbox_ownership_to_queue_without_claiming_processing(self):
        receipts = []
        with Outbox(self.spool, "edge-003") as outbox:
            outbox.sample(41)
            outbox.sample(42)
            with patch.dict(os.environ, {"EDGEOPS_API_TOKEN": "synthetic-test-token"}):
                acknowledged = outbox.flush(lambda batch: receipts.append(send_events(self.base, batch)))
            self.assertEqual(acknowledged, 2)
            self.assertEqual(outbox.pending_count(), 0)
            self.assertEqual(receipts[0]["delivery"], {"httpStatus": 202, "stage": "queued", "acknowledged": 2})
            self.assertNotIn("stats", receipts[0])
            self.assertEqual(self.requests[0]["authorization"], "Bearer synthetic-test-token")
            self.assertEqual(self.requests[0]["path"], "/api/telemetry")

    def test_202_with_incomplete_acknowledgement_retains_outbox(self):
        for payload in ({"accepted": 1, "messageId": "partial"}, {"accepted": 2},
                        {"accepted": True, "messageId": "bad-type"}):
            self.payload = payload
            with self.subTest(payload=payload), Outbox(self.spool, "edge-003") as outbox:
                if outbox.pending_count() == 0:
                    outbox.sample(41)
                    outbox.sample(42)
                with self.assertRaises(OSError):
                    outbox.flush(lambda batch: send_events(self.base, batch))
                self.assertEqual(outbox.pending_count(), 2)

    def test_cli_labels_queue_acceptance_without_claiming_processed_delivery(self):
        output = io.StringIO()
        argv = ["device_agent.py", "--url", self.base, "--spool", str(self.spool), "--count", "2"]
        with patch('sys.argv', argv), patch('sys.stdout', output):
            main()
        result = json.loads(output.getvalue())
        self.assertEqual(result['acknowledged'], 2)
        self.assertEqual(result['queued'], 2)
        self.assertEqual(result['processedOrDeduplicated'], 0)
        self.assertEqual(result['buffered'], 0)
        self.assertIn('not confirmed', result['note'])

    def test_503_retains_outbox_for_retry(self):
        self.status = 503
        self.payload = {"error": "temporarily unavailable"}
        with Outbox(self.spool, "edge-003") as outbox:
            outbox.sample(41)
            with self.assertRaises(OSError):
                outbox.flush(lambda batch: send_events(self.base, batch))
            self.assertEqual(outbox.pending_count(), 1)

    def test_unexpected_success_status_retains_outbox(self):
        self.status = 201
        with Outbox(self.spool, "edge-003") as outbox:
            outbox.sample(41)
            with self.assertRaises(OSError):
                outbox.flush(lambda batch: send_events(self.base, batch))
            self.assertEqual(outbox.pending_count(), 1)

    def test_redirect_is_not_followed_or_counted_as_delivery(self):
        self.status = 302
        with Outbox(self.spool, 'edge-003') as outbox:
            outbox.sample(41)
            with patch.dict(os.environ, {'EDGEOPS_API_TOKEN': 'synthetic-test-token'}), self.assertRaises(OSError):
                outbox.flush(lambda batch: send_events(self.base, batch))
            self.assertEqual(outbox.pending_count(), 1)
            self.assertEqual(len(self.requests), 1)


if __name__ == "__main__":
    unittest.main()
