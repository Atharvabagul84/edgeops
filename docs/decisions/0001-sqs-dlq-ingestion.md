# 0001: SQS with a dead-letter queue for cloud ingestion

**Status:** Accepted

## Context
Devices send batches after reconnecting, often in bursts. The API Lambda must answer quickly, and a malformed or failing batch must not block the rest or vanish silently.

## Decision
The API Lambda validates the request shape and enqueues telemetry to SQS, returning HTTP 202. A worker Lambda applies batches to DynamoDB using partial batch responses. Messages that keep failing move to a dead-letter queue, with a CloudWatch alarm on its depth.

## Consequences
- Bursts are absorbed by the queue; the API stays fast.
- Delivery is at-least-once, so the domain must be idempotent (per-device sequences and event IDs, see the README).
- "Accepted" (202) is not "applied": checks and docs confirm resulting sequences before claiming delivery.
- Forced-DLQ delivery and the alarm transition are still listed as not yet verified live (see [validation](../reference/validation.md)).
