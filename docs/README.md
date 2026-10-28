# EdgeOps documentation

## Project
- [Product requirements](PRD.md): what EdgeOps is for, users, scope
- [Architecture](ARCHITECTURE.md): components, data flow, tech stack
- [Design system](DESIGN_SYSTEM.md): dashboard colours, type, spacing

## Guides (how to do something)
- [Local demo](guides/local-demo.md): run the app and the edge agent offline
- [AWS deployment](guides/aws-deployment.md): deploy, operate and remove the AWS stack
- [Repository setup](guides/repository-setup.md): GitHub settings for this repo

## Reference (how it works)
- [Runbook](reference/runbook.md): operating the deployed and local app, HTTP API
- [CI pipeline](reference/ci-pipeline.md): GitHub Actions checks and the guarded Jenkins release
- [Validation record](reference/validation.md): what was verified, live vs local, and what wasn't
- [Limitations](reference/limitations.md): deliberate MVP limits

## Decisions
- [0001 SQS with a dead-letter queue for ingestion](decisions/0001-sqs-dlq-ingestion.md)
- [0002 Code-only release policy](decisions/0002-code-only-release-policy.md)
- [0003 Standard-library local mode](decisions/0003-stdlib-local-mode.md)

## Evidence and history
- [Evidence](evidence/): screenshots and recorded JSON reports (smoke checks, diagnostics, release rehearsal)
- [Release status at 0.3.0](history/release-status.md)
- Jenkins build reports: [`reports/pipeline/`](../reports/pipeline/)
