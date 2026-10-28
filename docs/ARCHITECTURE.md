# Architecture

## 01 System Overview
- **Local:** browser dashboard → Python standard-library HTTP server (`backend/server.py`) → domain logic (`backend/domain.py`, `fleet.py`, `telemetry.py`) → SQLite (`data/edgeops.sqlite3`)
- **Cloud:** browser (S3 + CloudFront) → Cognito sign-in → API Gateway (JWT authorizer) → API Lambda → DynamoDB; telemetry → SQS → worker Lambda → DynamoDB; failures → dead-letter queue; CloudWatch logs and alarms
- **Edge agent:** `scripts/device_agent.py` with its own SQLite outbox, sending batches with a Cognito token
- Domain code is independent of HTTP and storage; `backend/aws_handler.py` reuses it unchanged

## 02 Tech Stack
| Area | Tool |
|---|---|
| Backend | Python 3.11+ standard library (no runtime dependencies) |
| Frontend | Plain HTML/CSS/JS modules, tested with `node --test` (Node 20+) |
| Persistence | SQLite locally, DynamoDB in AWS (single state item, ≤350,000 bytes) |
| Messaging | Amazon SQS with a dead-letter queue |
| Auth | Amazon Cognito (admin-created users, no public sign-up) |
| IaC | Terraform 1.17.0, locked providers (`infra/.terraform.lock.hcl`) |
| Release | Local Jenkins 2.580.1 pipeline (`Jenkinsfile`, `scripts/pipeline.py`, `scripts/pipeline_policy.py`) |
| CI | GitHub Actions (`.github/workflows/ci.yml`): tests, Terraform fmt/validate, Docker health check |
| Container | Non-root image (`Dockerfile`), loopback health check |
| Region | AWS `ap-southeast-2` |

## 03 Project Structure
```
edgeops/
├ backend/       # Domain logic, HTTP handler, AWS Lambda adapter, SQLite repository
├ frontend/      # Dashboard (HTML/CSS/JS) and its tests
├ infra/         # Terraform for the AWS stack, adapter tests
├ scripts/       # Edge agent, release pipeline and policy, launchers
├ tests/         # Backend, agent and pipeline tests
├ dependencies/  # Locked runtime, image, plugin and provider manifests
├ reports/       # Recorded Jenkins build reports (evidence)
└ docs/          # Guides, reference, decisions, evidence
```

## 04 Data Flow
1. A device (simulated or the agent) produces readings with a per-device sequence and event ID
2. While offline, readings stay in the outbox; on reconnect they're sent in batches (≤100 events, ≤64 KiB)
3. Cloud: the API accepts the batch into SQS (HTTP 202); the worker validates and applies it
4. Events at or below a device's high-water mark, or with a seen event ID, are counted as duplicates and not applied
5. The agent deletes a batch only after acknowledgement; the dashboard shows state, incidents and counters

## 05 Scalability
- State is one DynamoDB item by design (small demo fleet). A production version splits snapshots, incidents and idempotency records into separate items and stores raw events separately
- Don't add new services or dependencies without updating this file and an ADR in `docs/decisions/`
