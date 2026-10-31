"""AWS transport adapter. AWS SDK clients are initialized only inside Lambda."""
import base64
import json
import logging
import math
import os

from .domain import public_state
from .dynamo_store import FleetStore
from .release import with_release
from .validation import utc_time, validate_events

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)
MAX_REQUEST_BYTES = 64 * 1024


class RequestError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def response(status, payload, headers=None):
    if 200 <= status < 300:
        payload = with_release(payload)
    return {"statusCode": status, "headers": {
        "Content-Type": "application/json", "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff", **(headers or {})},
        "body": json.dumps(payload, allow_nan=False)}


def parse_body(event):
    headers = {key.lower(): value for key, value in event.get("headers", {}).items()}
    if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise RequestError(415, "Use Content-Type: application/json.")
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        if len(raw) > 4 * ((MAX_REQUEST_BYTES + 2) // 3):
            raise RequestError(413, "Request body exceeds 64 KiB.")
        raw = base64.b64decode(raw, validate=True).decode("utf-8")
    if len(raw.encode("utf-8")) > MAX_REQUEST_BYTES:
        raise RequestError(413, "Request body exceeds 64 KiB.")
    try:
        payload = json.loads(raw)
    except (ValueError, RecursionError):
        raise RequestError(400, "Request must be valid UTF-8 JSON with finite numbers.") from None
    if not isinstance(payload, dict):
        raise ValueError("JSON object required")
    pending = [(payload, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 16:
            raise ValueError("Request JSON nesting exceeds 16 levels.")
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("Request JSON numbers must be finite.")
        if isinstance(item, (dict, list)):
            pending.extend((child, depth + 1) for child in
                           (item.values() if isinstance(item, dict) else item))
    return payload


def event_list(payload):
    events = payload.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 100:
        raise ValueError("events must contain between 1 and 100 telemetry events")
    if not all(isinstance(item, dict) for item in events):
        raise ValueError("Each telemetry event must be an object")
    return events


def handle_http(event, store, queue, queue_url=None):
    context = event.get("requestContext", {})
    claims = context.get("authorizer", {}).get("jwt", {}).get("claims", {})
    if not claims.get("sub"):
        return response(401, {"error": "Authentication required"})
    method = context.get("http", {}).get("method")
    path = event.get("rawPath", "")
    try:
        if method == "GET" and path == "/api/health":
            return response(200, {"status": "ok", "mode": "aws", "demo": True,
                                  "persistence": "dynamodb"})
        if method == "GET" and path in ("/api/state", "/api/export"):
            state = public_state(store.read())
            if path == "/api/export":
                state.update(exportedAt=utc_time(), diagnosticNote="Synthetic AWS-backed demonstration. Single shared fleet.")
                return response(200, state, {"Content-Disposition": 'attachment; filename="edgeops-diagnostics.json"'})
            return response(200, state)
        if method == "POST" and path in ("/api/actions", "/api/tick", "/api/reset"):
            command = parse_body(event)
            if path == "/api/tick":
                command = {"action": "tick", "steps": command.get("steps", 1)}
            elif path == "/api/reset":
                command = {"action": "reset"}
            return response(200, public_state(store.command(command)))
        if method == "POST" and path == "/api/telemetry":
            events = event_list(parse_body(event))
            events = validate_events(store.devices(), events)
            sent = queue.send_message(QueueUrl=queue_url or os.environ["QUEUE_URL"],
                                      MessageBody=json.dumps({"events": events}, allow_nan=False))
            return response(202, {"accepted": len(events), "messageId": sent["MessageId"]})
        return response(404, {"error": "Route not found"})
    except RequestError as exc:
        return response(exc.status, {"error": str(exc)})
    except (ValueError, UnicodeError) as exc:
        return response(400, {"error": str(exc)})
    except Exception as exc:
        LOG.error(json.dumps({"event": "request_failed", "errorType": type(exc).__name__}))
        return response(503, {"error": "Service unavailable; retry shortly"})


def handle_queue(event, store):
    failures = []
    for record in event["Records"]:
        try:
            events = event_list(json.loads(record["body"]))
            store.ingest(events)
        except Exception as exc:
            failures.append({"itemIdentifier": record["messageId"]})
            LOG.warning(json.dumps({"event": "telemetry_failed", "messageId": record["messageId"],
                                    "errorType": type(exc).__name__}))
    return {"batchItemFailures": failures}


def handler(event, context):
    import boto3  # Provided by the AWS Lambda Python runtime.
    store = FleetStore(boto3.client("dynamodb"), os.environ["FLEET_TABLE"])
    records = event.get("Records")
    if records and all(record.get("eventSource") == "aws:sqs" for record in records):
        return handle_queue(event, store)
    return handle_http(event, store, boto3.client("sqs"))
