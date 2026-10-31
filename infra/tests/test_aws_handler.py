"""Cloud adapter tests with deterministic AWS API fakes; no AWS account required."""
import importlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.memory_dynamo import MemoryDynamo  # noqa: E402


def reading(sequence, device_id="edge-003", **changes):
    value = dict(eventId=f"{device_id}-ext-{sequence}", deviceId=device_id, sequence=sequence,
                 at="2026-10-06T10:00:00Z", temperature=25, battery=99, signal=90)
    value.update(changes)
    return value


class Interleaved(MemoryDynamo):
    """Runs another writer just before the first matching write reaches the table."""

    def __init__(self, operation="PutItem", key="DEVICE#edge-001"):
        super().__init__()
        self.trigger, self.operation, self.key, self.conflicts = None, operation, key, 0

    def _maybe_interleave(self, operation, items):
        if self.trigger and operation == self.operation and any(
                item["pk"]["S"] == self.key and item["sk"]["S"] == "STATE" for item in items):
            trigger, self.trigger = self.trigger, None
            trigger()

    def put_item(self, **request):
        self._maybe_interleave("PutItem", [request["Item"]])
        try:
            return super().put_item(**request)
        except Exception:
            self.conflicts += 1
            raise

    def transact_write_items(self, TransactItems):
        self._maybe_interleave("TransactWriteItems", [entry["Put"]["Item"] for entry in TransactItems])
        try:
            return super().transact_write_items(TransactItems)
        except Exception:
            self.conflicts += 1
            raise


class StoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = importlib.import_module("backend.dynamo_store")
        cls.domain = importlib.import_module("backend.domain")

    def versions(self, db):
        return {key: int(item["version"]["N"]) for key, item in db.items.items() if "version" in item}

    def test_fleet_is_one_item_per_device_plus_a_registry_item(self):
        db = MemoryDynamo()
        self.mod.FleetStore(db, "test").command({"action": "heat", "deviceId": "edge-001"})
        self.assertEqual(db.keys(), ["DEVICE#edge-001|STATE", "DEVICE#edge-002|STATE",
                                     "DEVICE#edge-003|STATE", "FLEET|META"])

    def test_reads_never_write(self):
        db = MemoryDynamo()
        state = self.mod.FleetStore(db, "test").read()
        self.assertEqual(len(state["devices"]), 3)
        self.assertEqual(db.items, {})

    def test_retry_reapplies_operation_to_latest_state_without_losing_update(self):
        db = Interleaved()
        store, rival = self.mod.FleetStore(db, "test"), self.mod.FleetStore(db, "test")
        store.command({"action": "tick"})
        db.trigger = lambda: rival.command({"action": "disconnect", "deviceId": "edge-001"})
        state = store.command({"action": "heat", "deviceId": "edge-001"})
        self.assertEqual(db.conflicts, 1)
        device = state["devices"][0]
        self.assertFalse(device["connected"])
        self.assertTrue(state["_hot"]["edge-001"])
        self.assertEqual(device["buffered"], 1)

    def test_writes_to_different_devices_do_not_conflict(self):
        db = Interleaved(key="DEVICE#edge-002")
        store, rival = self.mod.FleetStore(db, "test"), self.mod.FleetStore(db, "test")
        store.command({"action": "tick"})
        db.trigger = lambda: rival.ingest([reading(100, "edge-001")])
        store.command({"action": "disconnect", "deviceId": "edge-002"})
        self.assertEqual(db.conflicts, 0)
        # A command's response is its own snapshot; a fresh read shows both writers.
        state = store.read()
        self.assertEqual(state["devices"][0]["sequence"], 100)
        self.assertFalse(state["devices"][1]["connected"])

    def test_tick_commits_every_device_in_one_transaction(self):
        db = Interleaved(operation="TransactWriteItems", key="DEVICE#edge-003")
        store, rival = self.mod.FleetStore(db, "test"), self.mod.FleetStore(db, "test")
        store.command({"action": "heat", "deviceId": "edge-001"})
        calls = db.calls.get("TransactWriteItems", 0)
        db.trigger = lambda: rival.command({"action": "disconnect", "deviceId": "edge-003"})
        state = store.command({"action": "tick", "steps": 2})
        self.assertEqual(db.conflicts, 1)
        self.assertEqual(db.calls["TransactWriteItems"] - calls, 2)
        # The cancelled attempt changed nothing, so the retry ticks exactly twice.
        self.assertEqual([device["sequence"] for device in state["devices"]], [15, 14, 12])
        self.assertEqual(state["devices"][2]["buffered"], 2)

    def test_storage_size_guard_prevents_oversized_dynamodb_item(self):
        db = MemoryDynamo()
        store = self.mod.FleetStore(db, "test")
        store.command({"action": "tick"})
        before = self.versions(db)
        original = self.mod.MAX_ITEM_BYTES
        self.mod.MAX_ITEM_BYTES = 1_000
        try:
            with self.assertRaisesRegex(ValueError, "limit reached"):
                store.command({"action": "heat", "deviceId": "edge-001"})
        finally:
            self.mod.MAX_ITEM_BYTES = original
        self.assertEqual(self.versions(db), before)

    def test_storage_outage_is_not_mistaken_for_optimistic_conflict(self):
        db = MemoryDynamo()
        store = self.mod.FleetStore(db, "test")
        store.command({"action": "tick"})
        attempts = []
        def unavailable(**kwargs):
            attempts.append(kwargs)
            raise RuntimeError("database unavailable")
        db.put_item = unavailable
        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            store.command({"action": "heat", "deviceId": "edge-001"})
        self.assertEqual(len(attempts), 1)

    def test_throttled_transaction_is_not_a_conflict(self):
        error = type("Cancelled", (Exception,), {"response": {
            "Error": {"Code": "TransactionCanceledException"},
            "CancellationReasons": [{"Code": "ConditionalCheckFailed"}, {"Code": "ThrottlingError"}]}})()
        self.assertFalse(self.mod.is_conflict(error))

    def test_ingest_writes_one_reading_item_per_accepted_event(self):
        db = MemoryDynamo()
        store = self.mod.FleetStore(db, "test")
        batch = [reading(100), reading(101), reading(100), reading(5, eventId="stale")]
        self.assertEqual(store.ingest(batch), 2)
        readings = db.keys("DEVICE#edge-003")
        self.assertEqual(readings[:2], ["DEVICE#edge-003|READING#000000#0000000000000100",
                                        "DEVICE#edge-003|READING#000000#0000000000000101"])
        state = store.read()
        self.assertEqual(state["stats"]["duplicates"], 2)
        # SQS redelivery of the same message is absorbed as duplicates.
        self.assertEqual(store.ingest(batch), 0)
        self.assertEqual(db.keys("DEVICE#edge-003"), readings)
        self.assertEqual(store.read()["stats"]["duplicates"], 6)
        self.assertEqual(store.read()["stats"]["ingested"], 38)

    def test_batch_spanning_devices_writes_each_device_separately(self):
        db = MemoryDynamo()
        store = self.mod.FleetStore(db, "test")
        store.command({"action": "tick"})
        before = self.versions(db)
        store.ingest([reading(100, "edge-001"), reading(100, "edge-002")])
        changed = {key for key, version in self.versions(db).items() if before.get(key) != version}
        self.assertEqual({dict(key)["pk"] for key in changed if dict(key)["sk"] == "STATE"},
                         {"DEVICE#edge-001", "DEVICE#edge-002"})
        self.assertEqual(db.calls.get("TransactWriteItems"), 2)  # seed + tick only

    def test_invalid_batch_is_rejected_before_any_device_write(self):
        db = MemoryDynamo()
        store = self.mod.FleetStore(db, "test")
        store.command({"action": "tick"})
        before = self.versions(db)
        with self.assertRaises(ValueError):
            store.ingest([reading(100, "edge-001"), reading(101, "edge-999")])
        self.assertEqual(self.versions(db), before)

    def test_acknowledge_by_incident_writes_only_the_owning_device(self):
        db = MemoryDynamo()
        store = self.mod.FleetStore(db, "test")
        incident = store.command({"action": "disconnect", "deviceId": "edge-002"})["incidents"][0]
        before = self.versions(db)
        state = store.command({"action": "acknowledge", "incidentId": incident["id"]})
        self.assertIsNotNone(state["incidents"][0]["acknowledgedAt"])
        changed = [dict(key)["pk"] for key, version in self.versions(db).items() if before[key] != version]
        self.assertEqual(changed, ["DEVICE#edge-002"])

    def test_invalid_commands_raise_domain_errors_without_writes(self):
        db = MemoryDynamo()
        store = self.mod.FleetStore(db, "test")
        store.command({"action": "tick"})
        before = self.versions(db)
        for command, message in [({"action": "explode"}, "Unknown action"),
                                 ({"action": "heat", "deviceId": "edge-999"}, "Unknown deviceId"),
                                 ({"action": "acknowledge", "incidentId": "missing"}, "No matching open incident"),
                                 ({"action": "acknowledge", "incidentId": 7}, "must be a string"),
                                 ({"action": "acknowledge", "deviceId": "edge-001"}, "No matching open incident"),
                                 ({"action": "tick", "steps": 0}, "steps must be")]:
            with self.subTest(command=command), self.assertRaisesRegex(ValueError, message):
                store.command(command)
        self.assertEqual(self.versions(db), before)

    def test_reset_reseeds_every_device_and_starts_a_new_reading_epoch(self):
        db = MemoryDynamo()
        store = self.mod.FleetStore(db, "test")
        store.ingest([reading(100)])
        store.command({"action": "disconnect", "deviceId": "edge-001"})
        state = store.command({"action": "reset"})
        self.assertTrue(all(device["connected"] for device in state["devices"]))
        self.assertEqual(state["stats"]["ingested"], 36)
        self.assertEqual(state["incidents"], [])
        store.ingest([reading(100)])
        self.assertIn("DEVICE#edge-003|READING#000001#0000000000000100", db.keys("DEVICE#edge-003"))

    def test_per_device_store_matches_the_whole_fleet_domain(self):
        """The same script through the domain and the store gives the same fleet."""
        script = [("command", {"action": "tick", "steps": 2}),
                  ("command", {"action": "disconnect", "deviceId": "edge-002"}),
                  ("command", {"action": "tick", "steps": 3}),
                  ("command", {"action": "heat", "deviceId": "edge-001"}),
                  ("ingest", [reading(100), reading(101), reading(100)]),
                  ("command", {"action": "reconnect", "deviceId": "edge-002"}),
                  ("command", {"action": "replay", "deviceId": "edge-003"}),
                  ("command", {"action": "acknowledge", "deviceId": "edge-001"}),
                  ("command", {"action": "cool", "deviceId": "edge-001"})]
        state = {**self.domain.initial_state(), "mode": "aws"}
        store = self.mod.FleetStore(MemoryDynamo(), "test")
        for kind, argument in script:
            if kind == "command":
                self.domain.apply_command(state, argument)
                cloud = store.command(argument)
            else:
                self.domain.ingest_events(state, argument)
                store.ingest(argument)
                cloud = store.read()
        fields = ("id", "connected", "status", "temperature", "battery", "signal", "sequence",
                  "buffered", "received")
        def view(fleet):
            return dict(devices=[{key: device[key] for key in fields} | {
                            "history": [point["temperature"] for point in device["history"]]}
                        for device in fleet["devices"]],
                        stats=fleet["stats"], pipeline=fleet["pipeline"],
                        incidents=sorted((item["deviceId"], item["kind"], item["status"],
                                          item["acknowledgedAt"] is None) for item in fleet["incidents"]),
                        events=sorted((event["deviceId"] or "", event["type"]) for event in fleet["events"]))
        self.assertEqual(view(cloud), view(state))


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
            def ingest(self, events):
                return len(events)
        result = self.mod.handle_queue({"Records": [
            {"messageId": "good", "body": '{"events": [{"id": "one"}]}'},
            {"messageId": "bad", "body": "not-json"},
        ]}, Store())
        self.assertEqual(result, {"batchItemFailures": [{"itemIdentifier": "bad"}]})

    def test_queue_worker_ingests_into_device_items(self):
        db = MemoryDynamo()
        store = self.mod.FleetStore(db, "test")
        result = self.mod.handle_queue({"Records": [
            {"messageId": "one", "body": json.dumps({"events": [reading(100)]})}]}, store)
        self.assertEqual(result, {"batchItemFailures": []})
        self.assertEqual(store.read()["devices"][2]["sequence"], 100)

    def test_authenticated_ingest_queues_and_returns_accepted(self):
        class Queue:
            def send_message(self, **kwargs):
                self.message = json.loads(kwargs["MessageBody"])
                return {"MessageId": "queued-1"}
        queue = Queue()
        db = MemoryDynamo()
        store = self.mod.FleetStore(db, "test")
        event = {"rawPath": "/api/telemetry", "body": json.dumps({"events": [reading(100, eventId="one")]}),
                 "headers": {"content-type": "application/json"},
                 "requestContext": {"http": {"method": "POST"},
                                    "authorizer": {"jwt": {"claims": {"sub": "demo"}}}}}
        result = self.mod.handle_http(event, store, queue, queue_url="test-url")
        self.assertEqual(result["statusCode"], 202)
        self.assertEqual(queue.message["events"][0]["eventId"], "one")
        self.assertEqual(db.calls, {"GetItem": 1})

    def test_reset_retains_cloud_mode_in_persisted_and_public_state(self):
        store = self.mod.FleetStore(MemoryDynamo(), "test")
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
