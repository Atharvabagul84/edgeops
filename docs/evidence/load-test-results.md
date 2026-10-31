# Store-layer load test results

**Status: not yet run against AWS.** The table below is empty on purpose. Fill it only from real DynamoDB runs, and commit the JSON (`--output`) next to this file.

The harness ([`scripts/store_loadtest.py`](../../scripts/store_loadtest.py)) drives the v1.0.0 single-item store and the per-device store ([ADR 0004](../decisions/0004-per-device-dynamodb-items.md)) directly, with concurrent writers that own disjoint devices, the way parallel SQS worker invocations would. It skips API Gateway: the stage throttles at 2 rps with a burst of 5 (`infra/api.tf`), so any HTTP load test would only measure that throttle.

## How to run (owner, costs money)

1. Create a separate on-demand table. The harness refuses table names without `loadtest`, so it can't touch the fleet table.
   ```bash
   aws dynamodb create-table --table-name edgeops-loadtest --region ap-southeast-2 \
     --billing-mode PAY_PER_REQUEST \
     --attribute-definitions AttributeName=pk,AttributeType=S AttributeName=sk,AttributeType=S \
     --key-schema AttributeName=pk,KeyType=HASH AttributeName=sk,KeyType=RANGE
   ```
2. Run it with `pip install boto3` and credentials for that account:
   ```bash
   python scripts/store_loadtest.py --backend dynamodb --table edgeops-loadtest --region ap-southeast-2 \
     --confirm-live --store both --devices 50 --workers 8 --ops 50 --batch 5 \
     --output docs/evidence/load-test-<date>.json
   ```
3. Delete the table: `aws dynamodb delete-table --table-name edgeops-loadtest --region ap-southeast-2`.

Rough cost for the default run: the 50-device single item is about 180 KB, so each baseline write costs about 180 write units. 400 batches × (1 + retries) comes to well under $1 on demand. The per-device run is a few cents.

## Results

| Backend | Store | Devices | Workers | Batch | OK / ops | Readings/s | p50 ms | p99 ms | Conflict rate | Throttles |
|---|---|---|---|---|---|---|---|---|---|---|
| dynamodb | legacy | | | | | | | | | |
| dynamodb | fleet | | | | | | | | | |

Conflict rate = conditional writes that lost an optimistic race ÷ all conditional writes. Each op that fails after six retries counts in "OK / ops".
