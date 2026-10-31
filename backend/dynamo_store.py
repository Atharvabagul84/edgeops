"""DynamoDB fleet store: one item per device and per accepted reading (ADR 0004).

    pk=FLEET          sk=META                     registry, reset epoch, system log
    pk=DEVICE#<id>    sk=STATE                    one single-device domain state + version
    pk=DEVICE#<id>    sk=READING#<epoch>#<seq>    one accepted telemetry reading (TTL)

Each device item holds a complete domain state for exactly one device, so the
unchanged domain functions run on it directly and fleet totals are sums. Writes
to different devices never conflict. The META item changes only on seed/reset.
"""
import json
import random
import time

from .domain import apply_command, ingest_events, initial_state
from .seed import DEVICES
from .validation import utc_time, validate_events

MAX_ITEM_BYTES = 350_000
READING_TTL_SECONDS = 7 * 24 * 3600
DEVICE_ACTIONS = ("disconnect", "reconnect", "heat", "cool", "replay")
STATS = ("ingested", "duplicates", "replayed", "buffered", "activeIncidents")
PIPELINE = ("accepted", "processed", "duplicates", "deadLetters")


def error_code(exc):
    return getattr(exc, "response", {}).get("Error", {}).get("Code")


def is_conflict(exc):
    """True only for a lost optimistic race, never for an outage or throttle."""
    code = error_code(exc)
    if code == "ConditionalCheckFailedException":
        return True
    if code == "TransactionCanceledException":
        reasons = [reason.get("Code") for reason in exc.response.get("CancellationReasons", [])]
        return any(reason in ("ConditionalCheckFailed", "TransactionConflict") for reason in reasons) and \
            all(reason in ("None", "ConditionalCheckFailed", "TransactionConflict") for reason in reasons)
    return False


def merge_fleet(meta, parts):
    """Assemble the dashboard's fleet state from META and single-device states."""
    events = list(meta["events"]) + [event for part in parts for event in part["events"]]
    incidents = [item for part in parts for item in part["incidents"]]
    return dict(
        mode=meta["mode"], demo=meta["demo"], dataSource=meta["dataSource"],
        now=max([meta["now"]] + [part["now"] for part in parts]),
        devices=[device for part in parts for device in part["devices"]],
        # Stable sorts keep each device's own newest-first order for equal timestamps.
        incidents=sorted(incidents, key=lambda item: (item["status"] == "open", item["openedAt"]), reverse=True)[:100],
        events=sorted(events, key=lambda event: event["at"], reverse=True)[:150],
        stats={key: sum(part["stats"][key] for part in parts) for key in STATS},
        pipeline={key: sum(part["pipeline"][key] for part in parts) + (meta["deadLetters"] if key == "deadLetters" else 0)
                  for key in PIPELINE},
        _seen=[event_id for part in parts for event_id in part["_seen"]],
        **{key: {k: v for part in parts for k, v in part[key].items()}
           for key in ("_outbox", "_lastEvents", "_nextSequences", "_hot", "_base")})


class FleetStore:
    """Per-device items with optimistic concurrency; same interface as StateRepository."""

    def __init__(self, client, table, definitions=DEVICES, mode="aws", namespace=""):
        self.client, self.table, self.definitions = client, table, tuple(definitions)
        self.mode, self.namespace = mode, namespace

    # Keys and serialization -------------------------------------------------
    def _key(self, pk, sk):
        return {"pk": {"S": self.namespace + pk}, "sk": {"S": sk}}

    def _meta_key(self):
        return self._key("FLEET", "META")

    def _device_key(self, device_id):
        return self._key("DEVICE#" + device_id, "STATE")

    def _put(self, key, version, body):
        payload = json.dumps(body, separators=(",", ":"), allow_nan=False)
        if len(payload.encode("utf-8")) > MAX_ITEM_BYTES:
            raise ValueError("Device state limit reached; export then reset the demo")
        request = {"TableName": self.table,
                   "Item": {**key, "version": {"N": str(version + 1)}, "payload": {"S": payload}}}
        if version:
            request.update(ConditionExpression="#v = :v", ExpressionAttributeNames={"#v": "version"},
                           ExpressionAttributeValues={":v": {"N": str(version)}})
        else:
            request["ConditionExpression"] = "attribute_not_exists(pk)"
        return request

    # Seeding ----------------------------------------------------------------
    def _seed_meta(self, at, epoch=0):
        state = {**initial_state(at, ()), "mode": self.mode}
        return dict(mode=self.mode, demo=state["demo"], dataSource=state["dataSource"], now=at,
                    events=state["events"], deadLetters=0, epoch=epoch,
                    deviceIds=[definition[0] for definition in self.definitions])

    def _seed_part(self, at, device_id, epoch):
        definition = next(item for item in self.definitions if item[0] == device_id)
        part = {**initial_state(at, (definition,)), "mode": self.mode, "_epoch": epoch}
        part["events"] = [event for event in part["events"] if event["deviceId"] is not None]
        return part

    # Reads ------------------------------------------------------------------
    def _load_meta(self):
        item = self.client.get_item(TableName=self.table, Key=self._meta_key(), ConsistentRead=True).get("Item")
        if item is None:
            return self._seed_meta(utc_time()), 0
        return json.loads(item["payload"]["S"]), int(item["version"]["N"])

    def _load_parts(self, meta, device_ids):
        """Consistent BatchGetItem by key; missing devices are seeded in memory (version 0)."""
        found, pending = {}, [self._device_key(device_id) for device_id in device_ids]
        while pending:
            batch, pending = pending[:100], pending[100:]
            request = {self.table: {"Keys": batch, "ConsistentRead": True}}
            for attempt in range(8):
                result = self.client.batch_get_item(RequestItems=request)
                for item in result.get("Responses", {}).get(self.table, []):
                    found[item["pk"]["S"][len(self.namespace) + len("DEVICE#"):]] = (
                        json.loads(item["payload"]["S"]), int(item["version"]["N"]))
                request = result.get("UnprocessedKeys") or {}
                if not request:
                    break
                time.sleep(random.uniform(0.01, 0.05) * (attempt + 1))
            else:
                raise RuntimeError("State busy; retry the request")
        return {device_id: found.get(device_id) or (self._seed_part(meta["now"], device_id, meta["epoch"]), 0)
                for device_id in device_ids}

    def _load_fleet(self):
        meta, meta_version = self._load_meta()
        return meta, meta_version, self._load_parts(meta, meta["deviceIds"])

    def devices(self, meta=None):
        """Registry-only state, enough for validate_events without loading the fleet."""
        meta = meta or self._load_meta()[0]
        return {"devices": [{"id": device_id} for device_id in meta["deviceIds"]], "incidents": []}

    def read(self):
        meta, _, parts = self._load_fleet()
        return merge_fleet(meta, [part for part, _ in parts.values()])

    # Writes -----------------------------------------------------------------
    def _commit(self, requests):
        if len(requests) == 1:
            self.client.put_item(**requests[0])
        elif requests:
            if len(requests) > 100:
                raise ValueError("A fleet-wide command can change at most 99 devices at once")
            self.client.transact_write_items(TransactItems=[{"Put": request} for request in requests])

    def _retry(self, attempt_once):
        for attempt in range(6):
            try:
                return attempt_once()
            except Exception as exc:
                if not is_conflict(exc):
                    raise
                time.sleep(random.uniform(0.005, 0.025) * (attempt + 1))
        raise RuntimeError("State busy; retry the request")

    def _ensure_seeded(self):
        """Create META and every device item once; losing the race is fine."""
        meta, meta_version = self._load_meta()
        if meta_version:
            return meta
        parts = self._load_parts(meta, meta["deviceIds"])
        requests = [self._put(self._meta_key(), 0, meta)]
        requests += [self._put(self._device_key(device_id), version, part)
                     for device_id, (part, version) in parts.items() if not version]
        try:
            for start in range(0, len(requests), 100):
                self._commit(requests[start:start + 100])
        except Exception as exc:
            if not is_conflict(exc):
                raise
        return meta

    def command(self, command):
        """Apply an operator command, writing only the device items it changes."""
        self._ensure_seeded()
        return self._retry(lambda: self._command_once(command))

    def _command_once(self, command):
        meta, meta_version, parts = self._load_fleet()
        action = command.get("action") if isinstance(command, dict) else None
        if action == "reset":
            return self._reset(meta, meta_version, parts)
        targets = self._targets(command, action, parts)
        if targets is None:
            # Invalid commands raise the domain's own validation error, without writes.
            apply_command(self.devices(meta), command)
            raise ValueError("Unsupported command.")
        at = utc_time()
        requests = []
        for device_id in targets:
            part, version = parts[device_id]
            before = json.dumps(part, sort_keys=True)
            apply_command(part, command, now=at)
            if json.dumps(part, sort_keys=True) != before:
                requests.append(self._put(self._device_key(device_id), version, part))
        self._commit(requests)
        return merge_fleet(meta, [part for part, _ in parts.values()])

    def _targets(self, command, action, parts):
        if action == "tick":
            return list(parts)
        if action in DEVICE_ACTIONS or action == "acknowledge":
            device_id, incident_id = command.get("deviceId"), command.get("incidentId")
            if action == "acknowledge" and isinstance(incident_id, str):
                return next(([owner] for owner, (part, _) in parts.items()
                             if any(item["id"] == incident_id and item["status"] == "open"
                                    for item in part["incidents"])), None)
            if action == "acknowledge" and incident_id is not None:
                return None
            if isinstance(device_id, str) and device_id in parts:
                return [device_id]
        return None

    def _reset(self, meta, meta_version, parts):
        at = utc_time()
        fresh = self._seed_meta(at, meta["epoch"] + 1)
        seeded = {device_id: self._seed_part(at, device_id, fresh["epoch"]) for device_id in fresh["deviceIds"]}
        if set(seeded) != set(parts):
            parts = self._load_parts(fresh, list(seeded))
        requests = [self._put(self._meta_key(), meta_version, fresh)]
        requests += [self._put(self._device_key(device_id), parts[device_id][1], part)
                     for device_id, part in seeded.items()]
        self._commit(requests)
        return merge_fleet(fresh, list(seeded.values()))

    def ingest(self, events):
        """Validate the whole batch, then ingest each device's readings independently.

        Ingestion is idempotent, so one device committing before another device's
        retry is safe; SQS redelivery of the whole batch only produces duplicates.
        """
        meta = self._ensure_seeded()
        validated = validate_events(self.devices(meta), events)
        accepted = 0
        for device_id in dict.fromkeys(event["deviceId"] for event in validated):
            group = [event for event in validated if event["deviceId"] == device_id]
            accepted += self._retry(lambda: self._ingest_once(meta, device_id, group))
        return accepted

    def _ingest_once(self, meta, device_id, events):
        part, version = self._load_parts(meta, [device_id])[device_id]
        seen = set(part["_seen"])
        ingest_events(part, events)
        accepted = {event["eventId"]: event for event in events
                    if event["eventId"] in part["_seen"] and event["eventId"] not in seen}
        # Readings are written before the device commit and are idempotent, so a
        # crash between the two is repaired by SQS redelivery.
        for event in accepted.values():
            self._put_reading(part["_epoch"], event)
        self._commit([self._put(self._device_key(device_id), version, part)])
        return len(accepted)

    def _put_reading(self, epoch, event):
        item = {**self._key("DEVICE#" + event["deviceId"], f"READING#{epoch:06d}#{event['sequence']:016d}"),
                "eventId": {"S": event["eventId"]}, "at": {"S": event["at"]},
                "reading": {"S": json.dumps(event, separators=(",", ":"), allow_nan=False)},
                "expiresAt": {"N": str(int(time.time()) + READING_TTL_SECONDS)}}
        try:
            self.client.put_item(TableName=self.table, Item=item, ConditionExpression="attribute_not_exists(pk)")
        except Exception as exc:
            if error_code(exc) != "ConditionalCheckFailedException":
                raise
