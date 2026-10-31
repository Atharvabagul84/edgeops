"""Store-layer load test: v1.0.0 single-item store vs per-device items.

Drives the stores directly with concurrent writers, the way parallel SQS worker
invocations would. It deliberately skips API Gateway, whose 2 rps / burst-5
throttle (infra/api.tf) would cap any HTTP test long before DynamoDB matters.

    # Offline, in-memory table with simulated round-trip latency (free):
    python scripts/store_loadtest.py --store both --devices 50 --workers 8 --ops 50

    # Real DynamoDB: a separate on-demand test table, never the fleet table. Costs money.
    python scripts/store_loadtest.py --backend dynamodb --table edgeops-loadtest \
        --region ap-southeast-2 --confirm-live --store both

Each op ingests one batch for one device. Workers own disjoint devices, so the
per-device store should see no conflicts while the single item conflicts on
every concurrent write. Results print as JSON plus a Markdown row.
"""
import argparse
import json
import math
import random
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.domain import apply_command, ingest_events, initial_state  # noqa: E402
from backend.dynamo_store import FleetStore, error_code, is_conflict  # noqa: E402
from scripts.memory_dynamo import MemoryDynamo  # noqa: E402

MAX_PAYLOAD_BYTES = 350_000


class SingleItemStore:
    """The v1.0.0 StateStore, kept only as the benchmark baseline.

    Unchanged except for the sort key (the test table has pk+sk) and a namespace.
    """

    def __init__(self, client, table, initializer, namespace=""):
        self.client, self.table, self.initializer = client, table, initializer
        self.key = {"pk": {"S": namespace + "STATE"}, "sk": {"S": "STATE"}}

    def _load(self):
        item = self.client.get_item(TableName=self.table, Key=self.key, ConsistentRead=True).get("Item")
        if item is None:
            return self.initializer(), 0
        return json.loads(item["payload"]["S"]), int(item["version"]["N"])

    def read(self):
        return self._load()[0]

    def update(self, operation):
        for attempt in range(6):
            state, version = self._load()
            result = operation(state)
            payload = json.dumps(result, separators=(",", ":"), allow_nan=False)
            if len(payload.encode("utf-8")) > MAX_PAYLOAD_BYTES:
                raise ValueError("Demo state limit reached; export then reset the demo")
            request = {"TableName": self.table,
                       "Item": {**self.key, "version": {"N": str(version + 1)}, "payload": {"S": payload}},
                       "ConditionExpression": "attribute_not_exists(pk)"}
            if version:
                request.update(ConditionExpression="#v = :v", ExpressionAttributeNames={"#v": "version"},
                               ExpressionAttributeValues={":v": {"N": str(version)}})
            try:
                self.client.put_item(**request)
                return result
            except Exception as exc:
                if error_code(exc) != "ConditionalCheckFailedException":
                    raise
                time.sleep(random.uniform(0.005, 0.025) * (attempt + 1))
        raise RuntimeError("State busy; retry the request")

    def command(self, command):
        return self.update(lambda state: apply_command(state, command))

    def ingest(self, events):
        return self.update(lambda state: ingest_events(state, events))


class CountingClient:
    """Counts conditional writes and lost races without changing behaviour."""

    def __init__(self, client):
        self.client, self.lock = client, threading.Lock()
        self.writes = self.conflicts = self.throttles = 0

    def __getattr__(self, name):
        return getattr(self.client, name)

    def _write(self, method, **request):
        try:
            return method(**request)
        except Exception as exc:
            with self.lock:
                self.conflicts += is_conflict(exc)
                self.throttles += error_code(exc) in ("ProvisionedThroughputExceededException", "ThrottlingException")
            raise
        finally:
            with self.lock:
                self.writes += 1

    def put_item(self, **request):
        return self._write(self.client.put_item, **request)

    def transact_write_items(self, **request):
        return self._write(self.client.transact_write_items, **request)


def definitions(count):
    return tuple((f"lt-{index:04d}", f"Load device {index}", "Synthetic", 20.0, 90, 90) for index in range(count))


def make_store(kind, client, table, devices, namespace):
    if kind == "fleet":
        return FleetStore(client, table, definitions=devices, namespace=namespace)
    return SingleItemStore(client, table, lambda: {**initial_state(None, devices), "mode": "aws"}, namespace)


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1)]


def run(kind, client, table, device_count, workers, ops, batch, namespace=""):
    devices = definitions(device_count)
    counting = CountingClient(client)
    store = make_store(kind, counting, table, devices, namespace)
    store.command({"action": "tick"})  # seed outside the measurement
    counting.writes = counting.conflicts = counting.throttles = 0
    latencies, errors, lock = [], [], threading.Lock()

    def worker(index):
        owned = [device[0] for position, device in enumerate(devices) if position % workers == index]
        sequences = {device_id: 1000 for device_id in owned}
        for op in range(ops):
            device_id = owned[op % len(owned)]
            events = []
            for _ in range(batch):
                sequences[device_id] += 1
                events.append(dict(eventId=f"{namespace}{device_id}-{sequences[device_id]}", deviceId=device_id,
                                   sequence=sequences[device_id], at="2026-10-31T00:00:00Z",
                                   temperature=21.5, battery=88, signal=91))
            started = time.perf_counter()
            try:
                store.ingest(events)
                elapsed = time.perf_counter() - started
                with lock:
                    latencies.append(elapsed)
            except Exception as exc:
                with lock:
                    errors.append(type(exc).__name__ + ": " + str(exc)[:80])

    if device_count < workers:
        raise ValueError("Use at least as many devices as workers")
    threads = [threading.Thread(target=worker, args=(index,)) for index in range(workers)]
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    duration = time.perf_counter() - started
    attempted = workers * ops
    return dict(store=kind, devices=device_count, workers=workers, batch=batch, ops=attempted,
                succeeded=len(latencies), failed=len(errors), errorSamples=sorted(set(errors))[:3],
                seconds=round(duration, 3), opsPerSecond=round(len(latencies) / duration, 1),
                readingsPerSecond=round(len(latencies) * batch / duration, 1),
                p50Ms=_ms(percentile(latencies, 0.50)), p95Ms=_ms(percentile(latencies, 0.95)),
                p99Ms=_ms(percentile(latencies, 0.99)),
                meanMs=_ms(statistics.fmean(latencies)) if latencies else None,
                conditionalWrites=counting.writes, conflicts=counting.conflicts, throttles=counting.throttles,
                conflictRate=round(counting.conflicts / counting.writes, 4) if counting.writes else None)


def _ms(seconds):
    return None if seconds is None else round(seconds * 1000, 2)


def markdown_row(backend, result):
    return (f"| {backend} | {result['store']} | {result['devices']} | {result['workers']} | {result['batch']} | "
            f"{result['succeeded']}/{result['ops']} | {result['readingsPerSecond']} | {result['p50Ms']} | "
            f"{result['p99Ms']} | {result['conflictRate']} | {result['throttles']} |")


def live_client(args):
    if not args.confirm_live:
        raise SystemExit("Refusing to touch AWS without --confirm-live (this costs money).")
    if "loadtest" not in args.table:
        raise SystemExit("Use a dedicated test table whose name contains 'loadtest', never the fleet table.")
    import boto3  # Only needed for live runs: pip install boto3
    return boto3.client("dynamodb", region_name=args.region)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store", choices=("legacy", "fleet", "both"), default="both")
    parser.add_argument("--backend", choices=("memory", "dynamodb"), default="memory")
    parser.add_argument("--table", default="edgeops-loadtest")
    parser.add_argument("--region", default="ap-southeast-2")
    parser.add_argument("--confirm-live", action="store_true")
    parser.add_argument("--latency-ms", type=float, default=5.0, help="memory backend: delay per call")
    parser.add_argument("--devices", type=int, default=50)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--ops", type=int, default=50, help="batches per worker")
    parser.add_argument("--batch", type=int, default=5, help="readings per batch")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    results = []
    for kind in (("legacy", "fleet") if args.store == "both" else (args.store,)):
        client = live_client(args) if args.backend == "dynamodb" else MemoryDynamo(args.latency_ms / 1000)
        namespace = f"lt-{int(time.time())}-{kind}-" if args.backend == "dynamodb" else ""
        results.append(run(kind, client, args.table, args.devices, args.workers, args.ops, args.batch, namespace))
    report = dict(backend=args.backend, latencyMs=args.latency_ms if args.backend == "memory" else None,
                  table=args.table if args.backend == "dynamodb" else None, results=results)
    print(json.dumps(report, indent=2))
    for result in results:
        print(markdown_row(args.backend, result))
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
