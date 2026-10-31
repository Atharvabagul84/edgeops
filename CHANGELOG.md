# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- Cloud sign-in is now a full-screen view instead of a card inside the dashboard. Signed out, the sidebar, topbar, release badge and owner identity are hidden; a navy panel explains the project and links to the source, screenshots, recovery demo and the one-command local run. Single column at 600px and below.
- The sign-in field is labelled **Email** (`type="email"`, `autocomplete="username"`) to match the Cognito pool's email usernames. The password field has a show/hide toggle and a Caps Lock hint, focus starts in the first field, and the heading is an `h1`.
- The sign-in screen says how to recover a forgotten or expired password: ask the workspace owner for a new temporary password (it expires after 1 day).

### Fixed
- The dashboard no longer flashes ("Local simulator", "Connecting to telemetry…") before `cloud-config.json` loads; a neutral loading screen shows until the mode is known.

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
