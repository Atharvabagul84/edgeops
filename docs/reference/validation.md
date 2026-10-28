# MVP validation - 6 October 2026

## Verified locally

The suites called by `scripts/check.ps1` completed successfully. The cloud-readiness pass used direct Python/Node commands after the tool's PowerShell startup stalled:

- 62 Python backend/edge-agent/pipeline tests, including pipeline deployment guards and release checks.
- 21 JavaScript frontend tests, including the diagnostics dialog and release badge states.
- 22 AWS adapter tests using local fakes; no AWS account used for these tests.
- Python source compilation.
- Terraform formatting with `terraform fmt -check` and provider schema validation with `terraform validate`.

All 105 automated tests passed in the final successful Jenkins build #8 on 6 October 2026: 62 Python backend/agent/pipeline, 21 frontend, and 22 AWS adapter tests. Coverage includes duplicate suppression, old-sequence rejection, atomic batches, concurrent SQLite mutations, durable offline state, HTTP validation, host/origin boundaries, path traversal, edge-agent replay over a real local HTTP connection, HTTP202 acknowledgement and failed-delivery retention, redirect rejection, frontend error behavior, HTML escaping, chart edge cases, timestamp freshness, cloud configuration validation, Cognito challenges/refresh/expiry, form rerender errors, cloud conflict retries, and partial SQS failure handling. Release tests distinguish matching, mismatched, unknown, pending and unavailable versions. Pipeline guards cover restricted deployment targets, rejected infrastructure changes, saved-plan/source integrity, Terraform identity/refresh-only metadata, and loopback Docker checks.

Terraform validation used Terraform 1.9.8, AWS provider 6.67.0 and archive provider 2.8.1. Normal `terraform init` subsequently completed after an approved sandbox exception for Windows temporary-file access, verified both providers as signed by HashiCorp, and generated `infra/.terraform.lock.hcl`. Formatting and provider-backed validation passed again with the normally installed providers, without development overrides.

## AWS deployment

Terraform applied successfully on 6 October 2026: **51 resources added**, in **Asia Pacific (Sydney), `ap-southeast-2`**, for AWS the EdgeOps project.

- Website: [EdgeOps on CloudFront](https://d3aum9pitkz6he.cloudfront.net).
- API base URL: `https://example123.execute-api.ap-southeast-2.amazonaws.com` (application routes require Cognito authentication).
- The account API verified an active Free plan, $100 available credits, and a plan expiration date of 6 April 2027. Credit exhaustion may end it earlier.
- Regional Lambda account limits were verified as 10 concurrent executions and 10 unreserved. This stack has no reserved concurrency; the SQS worker mapping caps concurrency at two.
- Infrastructure includes the private S3/CloudFront site, Cognito, HTTP API, two Lambda functions, SQS/DLQ, DynamoDB, logs and alarms.

The post-deployment `plan -input=false -no-color -detailed-exitcode`, run through the isolated workspace credential helper, returned **exit code 0: no changes**. Terraform refreshed the actual resources and found that they match the configuration. No further apply was run for this check.

## Live AWS checks

All **12 checks** in the [sanitized cloud smoke report](../evidence/cloud-smoke-report.json) passed. The test used an ephemeral Cognito operator, suppressed email delivery, deleted that operator afterward, and restored a clean three-device demonstration. No passwords, tokens or credentials are included in the report.

- Unauthenticated API access returned 401; Cognito authentication and authorized health/state access succeeded, with DynamoDB persistence and three devices.
- Reset/tick generated six new readings. A temperature warning could be acknowledged and resolved by recovery.
- Offline recovery replayed three persisted readings and left no buffered readings; replaying a duplicate did not process it again.
- Export included cloud metadata and a download response header.
- A telemetry batch returned 202 with two accepted events; the SQS worker processed both into state. Sending the duplicate batch suppressed at least two duplicates.
- An invalid telemetry batch returned 400 and left ingestion unchanged. Cleanup restored three devices and removed the ephemeral user.

Six public cloud checks also passed: website/config/JavaScript returned 200, cloud configuration selected AWS and Sydney, CSP/HSTS headers were present, direct S3 access returned 403, and unauthenticated API access returned 401. An API OPTIONS preflight returned 204 with the exact CloudFront origin allowed and the Authorization header permitted. The CloudFront sign-in page was visually checked in Chrome, with no browser console warnings or errors.

## Authenticated cloud browser checks

The user created a personal operator and signed in. The observed Chrome session showed **Sign out**, **AWS API connected**, three healthy devices, 36 readings, zero incidents and zero duplicates. The account/password setup itself happened outside the observed test, so the live first-password challenge is not claimed as verified.

- **Run recovery demo passed:** readings increased 36→45, duplicates 0→1, and three buffered readings were replayed. All three devices were healthy afterward, with no active incidents or remaining buffer. This verified authenticated browser API interaction and functional CORS.
- **Authenticated export passed:** the JSON diagnostics dialog opened. After Download JSON was clicked, the automation download-event notification timed out; independently, the actual 7,384-byte downloaded file was found and parsed successfully.
- The saved file contains `mode: aws`, `demo: true`, 45 ingested readings, one duplicate, three replayed readings, zero buffered readings, no active incidents, and `exportedAt: 2026-10-06T09:23:55.863Z`. An exact copy is included as [cloud-browser-diagnostics.json](../evidence/cloud-browser-diagnostics.json).
- Browser console warnings and errors remained empty. The user's session was left signed in on the recovery results.

The [cloud dashboard screenshot](../evidence/edgeops-cloud-dashboard.jpg) is included in the project package.

## Browser checks

Verified against the running local application:

- Recovery demo changed accepted readings36->45, duplicate count0->1, and restored all three devices with no pending buffer.
- Heating a device opened an incident; cooling it resolved that incident.
- Incident-to-device navigation works.
- Starting simulation advances telemetry; pausing stops generation.
- Native diagnostics download completed as `edgeops-diagnostics.json`; the downloaded file contains the synthetic-data marker, statistics, incidents and events.
- Desktop1366px, narrow573px, and mobile390px layouts reviewed. Narrow/mobile document width no longer overflows horizontally; the table has its own scroll container.
- Compact navigation retains accessible names. Browser console contained no warnings/errors during these checks.

The [example local diagnostic snapshot](../evidence/example-diagnostics.json) represents a local synthetic test run. The separate [cloud browser export](../evidence/cloud-browser-diagnostics.json) above was retrieved from the real AWS deployment and also contains synthetic device data.

## Cloud frontend browser checks using mocks

A disposable fixture under `work/` intercepted Cognito/API requests and used a separate local SQLite database. It displayed "LOCAL CLOUD-FLOW TEST — no AWS connection" throughout. No real credentials or external AWS requests were involved.

- Wrong credentials displayed the error on the current form, retained the username, and cleared the password.
- The temporary-password response displayed required email and new-password fields; completing them opened the protected dashboard.
- Manual generation increased processed readings36->39. The four-step recovery demonstration increased them39->48, blocked one duplicate, resolved the incident, and left every buffer empty.
- Signing out cleared the dashboard and restored the sign-in form.
- Mock-cloud console reported no warnings/errors. Local mode loaded correctly after a backend restart with the new explicit local configuration endpoint.
- The in-app browser did not confirm a Blob download event within10seconds during this mocked test. Cloud diagnostics therefore include a JSON preview/copy fallback and a separate download action. The subsequent real Chrome download was verified from the actual file, as recorded above.
- The final diagnostics dialog was opened successfully through authenticated mocked API requests and displayed the full fleet, incident history, processing counts and synthetic-data marker. Its explicit download also had no confirmed in-app download event; the JSON selection fallback remains available.

## Jenkins and Docker verification

The authenticated Windows Jenkins controller is running locally, using the persistent EdgeOps workspace. [Build #4](../../reports/pipeline/jenkins-edgeops-deploy-4/build-summary.json) completed with **SUCCESS** in **124.3 seconds**. The [sanitized build summary](../../reports/pipeline/jenkins-edgeops-deploy-4/build-summary.json) records all seven stage reports passing:

- All 99 tests passed: 61 Python tests, 18 frontend tests, and 20 AWS adapter tests. Python compilation also passed. See [test report](../../reports/pipeline/jenkins-edgeops-deploy-4/tests.json).
- A real Docker image was built and started on an automatically assigned IPv4 loopback port. `/api/health` returned 200, and the build's own container was removed afterward. See [Docker report](../../reports/pipeline/jenkins-edgeops-deploy-4/docker.json).
- The configured AWS account, Sydney region, active Free plan, and Terraform formatting/schema validation passed. See [Terraform validation report](../../reports/pipeline/jenkins-edgeops-deploy-4/terraform-validation.json).
- The [saved-plan review](../../reports/pipeline/jenkins-edgeops-deploy-4/plan-review.json) passed with zero proposed changes and an empty `refreshOnlyDrift` list. Terraform then executed that exact saved plan successfully with zero resource changes; see [apply report](../../reports/pipeline/jenkins-edgeops-deploy-4/apply.json).
- All six public checks passed without mutating the fleet; see [cloud smoke report](../../reports/pipeline/jenkins-edgeops-deploy-4/cloud-smoke.json).
- All three [authenticated health checks](../../reports/pipeline/jenkins-edgeops-deploy-4/authenticated-health.json) passed: unauthenticated requests returned 401, Cognito login succeeded, and the protected DynamoDB-backed fleet returned three devices. The temporary Cognito user was deleted, `fleetModified` was false, and no secrets were recorded.

The first build failed with `workspace: null` before running tests or changing AWS resources. Jenkins global environment configuration was then added so the pre-agent `customWorkspace` expression could resolve the project directory; no Jenkinsfile code correction was needed.

Build #2 subsequently stopped during plan review, before apply, because the guard did not handle Terraform 1.9.8's omitted unchanged caller identity and refresh-only metadata. The policy now accepts a refreshed prior-state identity only when the planned identity is omitted and no identity read/change is pending. Drift is informational only when the corresponding managed resource has a proposed `no-op`; this is not a general remote-drift audit. Proposed mutation restrictions remain unchanged.

Build #3 failed only at the final authenticated-health helper: importing `boto3` raised a `PermissionError` in the Jenkins process. The SDK directory ACL allowed the setup context but did not grant read/execute access to the native account running Jenkins. This happened before any temporary Cognito user was created. Read/execute access was corrected on the SDK files only, without changing pipeline source or deployment guards.

A focused authenticated-readiness check then passed in the Jenkins context, followed by the complete successful build #4 described above. Fleet data was not mutated, and temporary authentication-test users were removed. See [pipeline operation](../reference/ci-pipeline.md) for configuration and deployment restrictions.

## Actual release deployment

[Build #5](../../reports/pipeline/jenkins-edgeops-deploy-5/build-summary.json) completed with **SUCCESS** in **211.9 seconds**, after all 105 tests passed. Its [build summary](../../reports/pipeline/jenkins-edgeops-deploy-5/build-summary.json) and [apply report](../../reports/pipeline/jenkins-edgeops-deploy-5/apply.json) record seven updates: two Lambda functions and five existing frontend objects. No resources were created or destroyed and no permissions changed.

The [authenticated/release report](../../reports/pipeline/jenkins-edgeops-deploy-5/authenticated-health.json) records four passing checks, including release `edgeops-0.3.0`. Hashes for all 13 served frontend files and both Lambda code packages matched the checkpoint. The live browser displayed matching UI/API **0.3.0**, three healthy devices, 45 readings and one duplicate. The persisted fleet payload SHA-256 and revision **16** remained identical to the baseline; the temporary Cognito user was removed and `fleetModified` was false.

[Build #6](../../reports/pipeline/jenkins-edgeops-deploy-6/build-summary.json) then completed the rollback with **SUCCESS** in **222.3 seconds**. It passed all 99 baseline tests (61 Python, 18 frontend, 20 AWS adapter), all seven stage reports, and all four authenticated/release checks. The saved plan applied seven updates, and fleet revision stayed **16**. See the [rollback build summary](../../reports/pipeline/jenkins-edgeops-deploy-6/build-summary.json).

The already-loaded 0.3.0 UI displayed **API unknown** when the rolled-back API omitted release metadata. This is the expected legacy-release state, not a false match. The rollback was based on the exact 33-file source snapshot. Packaged screenshots show the [matching release](../evidence/edgeops-release-0.3.0.jpg) and [rollback detection](../evidence/edgeops-rollback-detection.jpg).

Build #7 stopped during the local HTTP action/tick/export/reset test with Windows socket error **10055**, before any AWS stage. All 11 focused server tests then passed unchanged when rerun in the Jenkins context. The evidence supports a transient failure but does not establish lasting socket or memory exhaustion; no source correction was made.

The exact 34-file 0.3.0 source checkpoint remained unchanged for [build #8](../../reports/pipeline/jenkins-edgeops-deploy-8/build-summary.json), which completed with **SUCCESS** in **177.5 seconds**. All 105 tests and seven stage reports passed, the saved plan executed seven AWS updates, the temporary authentication-test user was removed, and fleet data remained unchanged. See the [final build summary](../../reports/pipeline/jenkins-edgeops-deploy-8/build-summary.json).

The [consolidated release rehearsal report](../evidence/release-rehearsal.json) passed its independent comparison across builds #5, #6 and #8. It verifies all 13 frontend file hashes and both Lambda hashes against immutable checkpoints, the original rollback Lambda package from build #4, and identical 0.3.0 packages in builds #5 and #8. The final release is **0.3.0**. Fleet revision **16** and payload SHA-256 `4c3d529ca56a79551eebb5088b1c3b267cf424e4c6c9798c08171b98a6416daf` remained identical throughout. The report contains no credentials.

This exercise restored source snapshots and redeployed them through Jenkins/Terraform; it did not switch Lambda aliases or roll back the database. Its fixed fleet baseline has been archived so normal future telemetry changes do not invalidate subsequent builds. Packaged screenshots show the [restored release](../evidence/edgeops-release-restored.jpg) and [successful Jenkins run](../evidence/edgeops-jenkins-release-success.jpg).

## Explicitly not yet verified

- The first-login password challenge and actual expired-token behavior have not been observed against live AWS. The user completed account/password setup outside the observed test; their authenticated browser operation and saved export are verified above.
- Forced malformed-message delivery to the real DLQ and an alarm transition, concurrent cloud mutation stress, and a full credentials-in-logs audit have not been performed.
- Terraform teardown has not been executed against this deployment.
- No production load, uptime, commercial readiness, multi-tenant isolation or physical-device test is claimed.

At the time of this original deployment validation, no changes had been pushed to GitHub. AWS resources now exist and generate metered usage subject to account allowances and credits; no zero-cost or permanent-free claim is made.
