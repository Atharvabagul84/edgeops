# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] - 2026-10-28

First public release. Earlier development history (through application release 0.3.0) is kept in a private archive.

### Added
- Durable edge-agent outbox with acknowledgement-based replay and duplicate suppression.
- Incidents dashboard with a one-click recovery demo and diagnostics export.
- AWS serverless deployment on Terraform: S3 + CloudFront, Cognito, API Gateway, API and worker Lambdas, SQS with a dead-letter queue, DynamoDB, CloudWatch alarms.
- Guarded Jenkins release pipeline (code-only plan policy, smoke checks, artifact hash verification) with a recorded release → rollback → restore rehearsal.
- GitHub Actions CI: 105 tests, Terraform format and validate, Docker health check.
- Documentation: guides, reference, decision records, evidence; security and contributing guides; agent instructions with deny rules for the live stack.

[Unreleased]: https://github.com/Atharvabagul84/edgeops/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Atharvabagul84/edgeops/releases/tag/v1.0.0
