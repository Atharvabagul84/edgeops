# Product Requirements Document

## 01 Product Overview
- **Product Name:** EdgeOps
- **Tagline:** Device telemetry that survives dropped connections.
- **Description:** A fleet-reliability demo. Edge devices buffer readings in a durable outbox while offline, replay them on reconnect, and the backend suppresses duplicates idempotently. Operators see incidents and recovery evidence on a dashboard. Runs fully offline locally and on AWS serverless.

## 02 Problem
- Field devices lose connectivity; naive clients drop readings or resend them and get counted twice.
- Teams rarely prove delivery guarantees end to end, or rehearse a release and rollback before they need one.

## 03 Goal
- Show, with tests and recorded evidence, that no acknowledged reading is lost or double-counted across a disconnect, and that a release can be rolled back and restored with matching artifact hashes.

## 04 Target Users
- Platform/SRE engineers evaluating delivery-guarantee patterns
- Operators watching a device fleet (dashboard)
- Hiring reviewers assessing DevOps and AWS practice

## 05 Core Features (Version 1)
- **Durable outbox:** standalone agent buffers up to 10,000 readings in SQLite and deletes only acknowledged batches.
- **Idempotent ingestion:** monotonic per-device sequences, event-ID de-duplication, bounded history.
- **Incidents dashboard:** fleet state, offline and heat incidents, one-click recovery demo, diagnostics export.
- **AWS deployment:** S3 + CloudFront, Cognito, API Gateway, two Lambdas, SQS + DLQ, DynamoDB, CloudWatch alarms via Terraform.
- **Guarded release:** Jenkins pipeline limited to code-only updates, with smoke checks and hash verification.

## 06 Out of Scope (for now)
- Multi-tenancy, MFA, real device firmware or rollout
- Automatic heartbeat-based disconnect detection
- Lossless long-term telemetry archive, anomaly ML
- Production uptime or load claims

## 07 Success Metrics
- 105 automated tests pass on every pull request.
- Recovery demo: accepted readings rise by exactly the buffered count; duplicates are counted, never applied.
- Release → rollback → restore: all served frontend and Lambda hashes match each checkpoint, fleet data unchanged.
