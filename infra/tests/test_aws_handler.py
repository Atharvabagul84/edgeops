"""Cloud adapter tests with deterministic AWS API fakes; no AWS account required."""
import importlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class ConditionalConflict(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class FakeDynamo:
    def __init__(self):
        self.item = None
        self.conflict_once = False

    def get_item(self, **kwargs):
        assert kwargs["ConsistentRead"] is True
        return {"Item": self.item} if self.item else {}

    def put_item(self, **kwargs):
        if self.conflict_once:
            self.conflict_once = False
            self.item = {"pk": {"S": "STATE"}, "version": {"N": "1"},
                         "payload": {"S": '{"count": 40}'}}
            raise ConditionalConflict()
        assert "ConditionExpression" in kwargs
        self.item = kwargs["Item"]


class StoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = importlib.import_module("backend.aws_handler")

    def test_retry_reapplies_operation_to_latest_state_without_losing_update(self):
        db = FakeDynamo()
        db.conflict_once = True
        store = self.mod.StateStore(db, "test", initializer=lambda: {"count": 0})
        result = store.update(lambda state: {"count": state["count"] + 1})
        self.assertEqual(result, {"count": 41})
        self.assertEqual(db.item["version"]["N"], "2")

    def test_storage_size_guard_prevents_oversized_dynamodb_item(self):
        db = FakeDynamo()
        store = self.mod.StateStore(db, "test", initializer=lambda: {})
        with self.assertRaises(ValueError):
            store.update(lambda state: {"data": "x" * 350_001})
        self.assertIsNone(db.item)

    def test_storage_outage_is_not_mistaken_for_optimistic_conflict(self):
        db = FakeDynamo()
        def unavailable(**kwargs):
            raise RuntimeError("database unavailable")
        db.put_item = unavailable
        store = self.mod.StateStore(db, "test", initializer=lambda: {})
        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            store.update(lambda state: {"ok": True})


class RouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = importlib.import_module("backend.aws_handler")

    def test_missing_authorizer_claims_fails_closed(self):
        result = self.mod.handle_http({"rawPath": "/api/state", "requestContext": {
            "http": {"method": "GET"}}}, None, None)
        self.assertEqual(result["statusCode"], 401)

    def test_sqs_response_retries_only_failed_message(self):
        class Store:
            def update(self, operation):
                return operation({})
        original = self.mod.ingest_events
        self.mod.ingest_events = lambda state, events: state
        try:
            result = self.mod.handle_queue({"Records": [
                {"messageId": "good", "body": '{"events": [{"id": "one"}]}'},
                {"messageId": "bad", "body": "not-json"},
            ]}, Store())
        finally:
            self.mod.ingest_events = original
        self.assertEqual(result, {"batchItemFailures": [{"itemIdentifier": "bad"}]})

    def test_authenticated_ingest_queues_and_returns_accepted(self):
        class Queue:
            def send_message(self, **kwargs):
                self.message = json.loads(kwargs["MessageBody"])
                return {"MessageId": "queued-1"}
        queue = Queue()
        reading = dict(eventId="one", deviceId="edge-001", sequence=100,
                       at="2026-10-06T10:00:00Z", temperature=25, battery=99, signal=90)
        store = self.mod.StateStore(FakeDynamo(), "test")
        event = {"rawPath": "/api/telemetry", "body": json.dumps({"events": [reading]}),
                 "headers": {"content-type": "application/json"},
                 "requestContext": {"http": {"method": "POST"},
                                    "authorizer": {"jwt": {"claims": {"sub": "demo"}}}}}
        result = self.mod.handle_http(event, store, queue, queue_url="test-url")
        self.assertEqual(result["statusCode"], 202)
        self.assertEqual(queue.message["events"][0]["eventId"], "one")

    def test_reset_retains_cloud_mode_in_persisted_and_public_state(self):
        db = FakeDynamo()
        store = self.mod.StateStore(db, "test", initializer=lambda: {
            **self.mod.initial_state(), "mode": "aws"})
        event = {"rawPath": "/api/actions", "body": '{"action": "reset"}',
                 "headers": {"content-type": "application/json"},
                 "requestContext": {"http": {"method": "POST"},
                                    "authorizer": {"jwt": {"claims": {"sub": "demo"}}}}}
        result = self.mod.handle_http(event, store, None)
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(json.loads(result["body"])["mode"], "aws")
        self.assertEqual(store.read()["mode"], "aws")


if __name__ == "__main__":
    unittest.main()
