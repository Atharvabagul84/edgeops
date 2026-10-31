"""API contract tests using real domain validation and an in-memory AWS store."""
import base64
import json
import unittest

from test_aws_handler import MemoryDynamo
from backend import aws_handler


class Queue:
    def __init__(self):
        self.messages = []

    def send_message(self, **kwargs):
        self.messages.append(json.loads(kwargs["MessageBody"]))
        return {"MessageId": "queued-one"}


class CloudContractTests(unittest.TestCase):
    def setUp(self):
        self.db, self.queue = MemoryDynamo(), Queue()
        self.store = aws_handler.FleetStore(self.db, "test")

    def request(self, method, path, payload=None, **overrides):
        event = {"rawPath": path, "body": json.dumps(payload or {}),
                 "headers": {"content-type": "application/json"},
                 "requestContext": {"http": {"method": method},
                    "authorizer": {"jwt": {"claims": {"sub": "operator"}}}}}
        event.update(overrides)
        return aws_handler.handle_http(event, self.store, self.queue, queue_url="test")

    def test_tick_alias_applies_steps_and_returns_public_state(self):
        before = self.store.read()["stats"]["ingested"]
        result = self.request("POST", "/api/tick", {"steps": 2})
        self.assertEqual(result["statusCode"], 200)
        state = json.loads(result["body"])
        self.assertEqual(state["stats"]["ingested"], before + 6)
        self.assertNotIn("_seen", state)

    def test_reset_alias_replaces_persisted_state_but_keeps_cloud_mode(self):
        self.request("POST", "/api/actions", {"action": "disconnect", "deviceId": "edge-001"})
        result = self.request("POST", "/api/reset")
        self.assertEqual(result["statusCode"], 200)
        state = json.loads(result["body"])
        self.assertEqual(state["mode"], "aws")
        self.assertTrue(all(device["connected"] for device in state["devices"]))

    def test_export_has_metadata_and_download_filename(self):
        result = self.request("GET", "/api/export")
        state = json.loads(result["body"])
        self.assertIn("exportedAt", state)
        self.assertIn("AWS", state["diagnosticNote"])
        self.assertEqual(result["headers"]["Content-Disposition"],
                         'attachment; filename="edgeops-diagnostics.json"')
        self.assertNotIn("exportedAt", self.store.read())

    def test_health_reports_matching_mode_and_persistence_fields(self):
        state = json.loads(self.request("GET", "/api/health")["body"])
        self.assertEqual(state, {"status": "ok", "mode": "aws", "demo": True,
                                "persistence": "dynamodb", "release": {"version": "0.3.0", "id": "edgeops-0.3.0"}})

    def test_release_identifies_success_responses_without_persisting_with_fleet(self):
        requests = [('GET', '/api/health', None), ('GET', '/api/state', None),
                    ('GET', '/api/export', None), ('POST', '/api/reset', {}),
                    ('POST', '/api/tick', {'steps': 1}),
                    ('POST', '/api/actions', {'action': 'disconnect', 'deviceId': 'edge-001'})]
        for method, path, payload in requests:
            with self.subTest(path=path):
                result = self.request(method, path, payload)
                self.assertEqual(result['statusCode'], 200)
                self.assertEqual(json.loads(result['body']).get('release'),
                                 {'version': '0.3.0', 'id': 'edgeops-0.3.0'})
                self.assertNotIn('release', self.store.read())

    def test_queued_receipt_reports_release_without_enriching_queued_readings(self):
        reading = dict(eventId='release-contract', deviceId='edge-003', sequence=100,
                       at='2026-10-06T10:00:00Z', temperature=25, battery=99, signal=90)
        result = self.request('POST', '/api/telemetry', {'events': [reading]})
        self.assertEqual(result['statusCode'], 202)
        receipt = json.loads(result['body'])
        self.assertEqual(receipt.get('release'), {'version': '0.3.0', 'id': 'edgeops-0.3.0'})
        self.assertEqual(receipt['accepted'], 1)
        self.assertNotIn('release', self.queue.messages[0])
        self.assertNotIn('release', self.queue.messages[0]['events'][0])
        self.assertEqual(self.db.items, {})

    def test_invalid_telemetry_is_rejected_before_queueing_or_mutation(self):
        result = self.request("POST", "/api/telemetry", {"events": [{"eventId": "missing-fields"}]})
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(self.queue.messages, [])
        self.assertEqual(self.db.items, {})

    def test_malformed_telemetry_body_is_rejected_before_any_database_read(self):
        class UnavailableStore:
            def devices(self):
                raise RuntimeError("database unavailable")
        self.store = UnavailableStore()
        result = self.request("POST", "/api/telemetry", body="not-json")
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(self.queue.messages, [])

    def test_entire_batch_is_validated_before_queueing(self):
        reading = dict(eventId="valid", deviceId="edge-001", sequence=100,
                       at="2026-10-06T10:00:00Z", temperature=25, battery=99, signal=90)
        result = self.request("POST", "/api/telemetry", {"events": [reading, {"eventId": "bad"}]})
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(self.queue.messages, [])

    def test_wrong_content_type_returns_415(self):
        result = self.request("POST", "/api/tick", headers={"content-type": "text/plain"})
        self.assertEqual(result["statusCode"], 415)

    def test_oversized_body_returns_413(self):
        result = self.request("POST", "/api/actions", body="x" * 65537)
        self.assertEqual(result["statusCode"], 413)

    def test_nonfinite_json_is_rejected_even_in_ignored_field(self):
        result = self.request("POST", "/api/actions", body='{"action":"tick","ignored":NaN}')
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(self.db.items, {})

    def test_deeply_nested_json_is_rejected(self):
        body = '{"action":"tick","nested":' + '[' * 20 + '0' + ']' * 20 + '}'
        result = self.request("POST", "/api/actions", body=body)
        self.assertEqual(result["statusCode"], 400)

    def test_base64_json_is_supported(self):
        encoded = base64.b64encode(b'{"steps":1}').decode()
        result = self.request("POST", "/api/tick", body=encoded, isBase64Encoded=True)
        self.assertEqual(result["statusCode"], 200)

    def test_explicit_empty_body_is_invalid_json(self):
        result = self.request("POST", "/api/actions", body="")
        self.assertEqual(result["statusCode"], 400)


if __name__ == "__main__":
    unittest.main()
