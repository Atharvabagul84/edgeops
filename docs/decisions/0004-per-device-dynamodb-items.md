# 0004: One DynamoDB item per device and per reading

**Status:** Accepted (2026-10-31). Supersedes the single-item store shipped in v1.0.0.

## Context
v1.0.0 kept the whole fleet in one item (`pk = "STATE"`, a JSON blob with an optimistic `version`). Every write from every device raced on that one key, and the item was capped at 350 KB, so the fleet could not grow. A fleet store needs:
- writes for different devices that never conflict;
- duplicate suppression that survives SQS at-least-once delivery;
- the existing `GET /api/state` fleet view, without forking the domain logic per adapter.

The two standard options were:
- **A. GSI + Query for fleet reads.** Put a constant `gsi1pk = FLEET` on each device item and Query the index to list devices.
- **B. `TransactWriteItems` for every write.** Write the event item (`attribute_not_exists`) and the device-state update in one transaction.

## Decision
Neither as the default. Instead:

| Item | Key | Written by |
|---|---|---|
| Fleet registry | `pk=FLEET`, `sk=META` | seed and reset only |
| Device state | `pk=DEVICE#<id>`, `sk=STATE` | every command or ingest for that device, guarded by `version` |
| Reading | `pk=DEVICE#<id>`, `sk=READING#<epoch>#<seq>` | ingest, `attribute_not_exists(pk)`, 7-day TTL |

- **Each device item is a full single-device domain state**, so `apply_command` and `ingest_events` run on it unchanged. Fleet totals are sums over devices (`merge_fleet`), and incidents and the activity log are merged from each device's own list.
- **Single-device writes use one conditional `PutItem`.** Device actions and SQS ingest touch one item. A batch that covers several devices is split by device. Each part retries on its own, which is safe because ingest is idempotent (the sequence high-water mark plus event IDs).
- **Reading items are idempotent puts written before the device commit.** If the Lambda dies between the two, SQS redelivers. The reading put becomes a no-op and the device commit goes through. Reset bumps `epoch`, so re-seeded sequences never collide with old readings.
- **`TransactWriteItems` is used only where it is needed:** `tick` and `reset` change every device and are not idempotent. A partial commit followed by a retry would tick some devices twice.
- **Fleet reads use the registry plus a consistent `BatchGetItem` by key.** No GSI.

## Why not A (GSI)
- GSIs are eventually consistent. The optimistic-concurrency read must be strongly consistent.
- Every device write would also write the index: twice the WCU for no gain while the registry fits in one item.
- A single constant GSI partition key (`FLEET`) brings the hot key back on the index.

## Why not B (transactions everywhere)
- A transaction costs twice the WCU of each item, and a transaction holds at most 100 items. A 100-event batch plus the state item doesn't fit.
- When one reading is a duplicate, the whole transaction is cancelled. Duplicates are the normal case after SQS redelivery, so the code would have to parse `CancellationReasons` for every replay.
- The device item's version check already gives per-device atomicity. A transaction would only add atomicity between the reading archive and the state, and the idempotent ordering gives that eventually.

## Consequences
- Writes scale with the number of devices; only writers to the same device can conflict. `scripts/store_loadtest.py` measures this against the v1.0.0 baseline.
- A command's HTTP response is a snapshot taken at its read, plus its own write. Concurrent writes to other devices appear on the next read.
- `GET /api/state` reads 1 + N items (N = device count). This is fine for the demo. Past about 10,000 devices the registry outgrows one item: shard the registry, or add a sparse GSI for listing only (eventual consistency is acceptable for a list).
- `tick` and `reset` are limited to 99 devices per transaction. They are simulator commands, not ingestion.
- The table is `PAY_PER_REQUEST`. This avoids throttling under a load test, and demo traffic costs cents. PITR is on (`point_in_time_recovery`). The v1.0.0 table leaves Terraform state through a `removed` block with `destroy = false`, so the previous release can still be restored. Delete it by hand after the cut-over.
- The local SQLite mode is unchanged. It keeps one row with a real transaction (ADR 0003).
