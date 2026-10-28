# Release status and cloud architecture notes

Moved from the README on 2026-10-25. Describes the original deployment environment as recorded.

**Current status:** release **0.3.0** is running on AWS in Sydney (`ap-southeast-2`). Jenkins successfully deployed it, rolled back to the original baseline, and restored it through builds **#5, #6 and #8**. The final [build #8](../../reports/pipeline/jenkins-edgeops-deploy-8/build-summary.json) passed 105 tests and completed in **177.5 seconds**. Deployed frontend/Lambda hashes verified the exact release and rollback artifacts; fleet data and revision 16 stayed unchanged throughout. See the [sanitized rehearsal evidence](../evidence/release-rehearsal.json). No AWS account is needed to run the local MVP. Source is maintained in the private Atharvabagul84/edgeops repository.

For a fresh clone, see [repository setup](../guides/repository-setup.md). Local run/test commands need no AWS account. Historical deployment records below describe the original environment; cloning does not restore its credentials, state or running Jenkins controller.

## Live AWS demo

Open [EdgeOps on AWS](https://d3aum9pitkz6he.cloudfront.net). The dashboard requires an admin-created Cognito operator account; public signup is disabled. The project uses the AWS Free plan with an initial $100 credit grant and a verified plan end date of 6 April 2027, or earlier if credits run out. This is not a promise of permanent free hosting.

See [deployment and account details](../guides/aws-deployment.md) for access, costs and teardown, and [validation results](../reference/validation.md) for the distinction between completed checks and pending cloud acceptance tests.


## Cloud architecture notes


The frontend is dependency-free HTML/CSS/JavaScript. Python's standard library provides the local HTTP server and SQLite. Domain logic is separate from HTTP and persistence, allowing reuse by the included AWS adapter.

The deployed path serves the frontend through private S3 and CloudFront, authenticates operators with Cognito, and uses API Gateway → Lambda → DynamoDB for state. Telemetry enters SQS before a separate Lambda worker writes state; failed messages can reach a DLQ. CloudWatch provides logs and alarms.

See [AWS deployment preparation](../guides/aws-deployment.md) for account setup, Terraform commands, authentication, cost controls, and cloud acceptance checks. See [operating runbook](../reference/runbook.md) for troubleshooting and demonstrations.

The deployed frontend reads Terraform-generated `cloud-config.json`. It signs into Cognito before loading the shared fleet; passwords and tokens are not stored in browser storage. Reloading requires sign-in. Cloud mode generates readings only on request and polls every 30 seconds while visible. Dashboard recovery actions are synchronous; the standalone agent uses the asynchronous SQS pipeline. HTTP202 confirms queue acceptance, not completed processing. The agent retains readings if authentication or delivery fails. Actual dead-letter depth is available in CloudWatch, not the dashboard counters.

Release 0.3.0 displays the loaded UI version and the API-reported version. The badge distinguishes a match, a mismatch, missing legacy metadata, and an API release that is pending or unverified after an error. Signing out clears the API release claim.

