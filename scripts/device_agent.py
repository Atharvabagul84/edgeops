"""A real durable edge outbox. No dependency or AWS account required."""
import argparse
import json
import math
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        # Do not forward a JWT to another endpoint or turn telemetry POST into GET.
        return None


_http = build_opener(_RejectRedirects())


class Outbox:
    def __init__(self, path, device_id):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.device_id = device_id
        self.connection = sqlite3.connect(path, timeout=10)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY, device TEXT, sequence INTEGER, payload TEXT)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)")
        self.connection.commit()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.connection.close()

    def _metadata(self, name, default=None):
        row = self.connection.execute("SELECT value FROM metadata WHERE key=?", (f"{self.device_id}:{name}",)).fetchone()
        return json.loads(row[0]) if row else default

    def _save_metadata(self, name, value):
        self.connection.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (f"{self.device_id}:{name}", json.dumps(value)))

    def sample(self, temperature):
        if not math.isfinite(temperature) or not -50 <= temperature <= 150:
            raise ValueError("Temperature must be finite and between -50 and 150 C")
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            if self.pending_count() >= 10000:
                raise ValueError("Outbox capacity reached; flush before generating more data")
            sequence = max(int(time.time() * 1000), self._metadata("sequence", 0) + 1)
            event = {
                "eventId": str(uuid.uuid4()), "deviceId": self.device_id,
                "sequence": sequence, "at": datetime.now(timezone.utc).isoformat(),
                "temperature": temperature, "battery": 88, "signal": 92,
            }
            self.connection.execute("INSERT INTO outbox VALUES (?,?,?,?)", (event["eventId"], self.device_id, sequence, json.dumps(event)))
            self._save_metadata("sequence", sequence)
        return event

    def pending_count(self):
        return self.connection.execute("SELECT count(*) FROM outbox WHERE device=?", (self.device_id,)).fetchone()[0]

    def flush(self, sender, batch_size=100):
        if not 1 <= batch_size <= 100:
            raise ValueError("Batch size must be between 1 and 100")
        delivered = 0
        while True:
            rows = self.connection.execute("SELECT id,payload FROM outbox WHERE device=? ORDER BY sequence LIMIT ?", (self.device_id, batch_size)).fetchall()
            if not rows:
                return delivered
            events = [json.loads(row[1]) for row in rows]
            sender(events)
            # A local 200 acknowledges processing/deduplication. A cloud 202
            # transfers ownership to the durable queue, not to a completed
            # processor. If this process dies before commit, replay is safe
            # because the processor deduplicates event IDs and sequences.
            with self.connection:
                self.connection.executemany("DELETE FROM outbox WHERE id=?", [(row[0],) for row in rows])
                self._save_metadata("last", events[-1])
            delivered += len(rows)

    def last_delivered(self):
        return self._metadata("last")


def send_events(base_url, events):
    endpoint = urlsplit(base_url)
    local = endpoint.hostname in ("127.0.0.1", "localhost", "::1")
    if not endpoint.hostname or (endpoint.scheme != "https" and not (endpoint.scheme == "http" and local)):
        raise ValueError("Use an HTTPS cloud URL or a loopback HTTP URL.")
    if endpoint.username is not None or endpoint.password is not None or endpoint.query or endpoint.fragment:
        raise ValueError("The API URL must not contain credentials, a query, or a fragment.")
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("EDGEOPS_API_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(base_url.rstrip("/") + "/api/telemetry", data=json.dumps({"events": events}).encode(), headers=headers, method="POST")
    with _http.open(request, timeout=15) as response:
        if response.status not in (200, 202):
            raise OSError(f"Backend did not acknowledge delivery: HTTP {response.status}")
        payload = json.load(response)
        if not isinstance(payload, dict):
            raise OSError("Backend acknowledgement must be a JSON object.")
        if response.status == 202:
            if type(payload.get("accepted")) is not int or payload["accepted"] != len(events):
                raise OSError("Queue did not acknowledge the complete event batch; readings retained.")
            if not isinstance(payload.get("messageId"), str) or not payload["messageId"].strip():
                raise OSError("Queue acknowledgement has no messageId; readings retained.")
            stage = "queued"
        else:
            if not isinstance(payload.get("stats"), dict) or type(payload["stats"].get("ingested")) is not int:
                raise OSError("Local response has no valid processing statistics; readings retained.")
            stage = "processed-or-deduplicated"
        payload["delivery"] = {"httpStatus": response.status, "stage": stage, "acknowledged": len(events)}
        return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765",
                        help="Local loopback URL or HTTPS API endpoint; JWT comes from EDGEOPS_API_TOKEN")
    parser.add_argument("--device", default="edge-003", choices=["edge-001", "edge-002", "edge-003"])
    parser.add_argument("--spool", default="data/device-agent.sqlite3")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--temperature", type=float, default=42)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--offline", action="store_true", help="Persist readings without attempting a network request")
    modes.add_argument("--flush-only", action="store_true", help="Send existing buffered readings without generating new ones")
    modes.add_argument("--replay-last", action="store_true", help="Resend the last delivered ID to demonstrate duplicate suppression")
    args = parser.parse_args()
    if not 1 <= args.count <= 1000:
        parser.error("--count must be between 1 and 1000")
    try:
        with Outbox(args.spool, args.device) as outbox:
            if args.replay_last:
                event = outbox.last_delivered()
                if event is None:
                    parser.error("No delivered event exists in this outbox")
                state = send_events(args.url, [event])
                note = ("Replay queued; processing is not confirmed. Check the fleet state or queue metrics." if state["delivery"]["stage"] == "queued"
                        else "Replay processed or deduplicated. Compare ingested and duplicate counts.")
                print(json.dumps({"replayedEvent": event["eventId"], "delivery": state["delivery"],
                                  "serverStats": state.get("stats", {}), "note": note}))
                return
            if not args.flush_only:
                for _ in range(args.count):
                    outbox.sample(args.temperature)
            counts = {"queued": 0, "processedOrDeduplicated": 0}
            def send_batch(events):
                result = send_events(args.url, events)
                key = "queued" if result["delivery"]["stage"] == "queued" else "processedOrDeduplicated"
                counts[key] += result["delivery"]["acknowledged"]
                return result
            acknowledged = 0 if args.offline else outbox.flush(send_batch)
            note = ("Queue acceptance confirmed; processing is not confirmed. Check fleet state or queue metrics."
                    if counts["queued"] else "Local processing/deduplication acknowledged." if acknowledged
                    else "Readings remain local until acknowledged by the API.")
            print(json.dumps({"deviceId": args.device, "acknowledged": acknowledged, **counts,
                              "buffered": outbox.pending_count(), "mode": "offline" if args.offline else "connected", "note": note}))
    except (OSError, ValueError, HTTPError, URLError) as error:
        print(json.dumps({"error": str(error), "note": "Unacknowledged readings remain in the durable outbox."}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
