# Local Jenkins pipeline

EdgeOps has a Jenkins controller on this Windows computer at `http://127.0.0.1:8080` (local to the owner's machine; not reachable from GitHub). It requires authentication and runs the project's [Jenkinsfile](../../Jenkinsfile) against the existing local source and deployed AWS stack. No GitHub checkout or additional AWS server is used.

**Build verification:** release, rollback and restoration all completed with **SUCCESS**. The final [build #8](../../reports/pipeline/jenkins-edgeops-deploy-8/build-summary.json) restored **0.3.0** in **177.5 seconds**, passing 105 tests and all seven stage reports. Each release/rollback run applied seven updates to two Lambda functions and five existing frontend objects, with no resource creation/deletion or permission changes. Six public checks and four authenticated/release checks passed; temporary Cognito users were removed and fleet data was unchanged. See the [consolidated rehearsal evidence](../evidence/release-rehearsal.json) and [final build summary](../../reports/pipeline/jenkins-edgeops-deploy-8/build-summary.json).

## Run a build

1. Keep Docker Desktop running and Jenkins open on this computer. Sign in using the local Jenkins credentials created during setup; these are separate from the EdgeOps Cognito operator account. Their local access record is private at `work/jenkins-access.json`.
2. Open the `edgeops-deploy` job and choose **Build with Parameters**.
3. Leave **DEPLOY_AWS** unchecked for tests, a Docker health check, Terraform validation and plan review, and checks of the existing cloud deployment. This setting does not apply the Terraform plan.
4. Select **DEPLOY_AWS** only when you intend to deploy changes to the existing application. The pipeline still rejects changes outside its code-only policy.
5. Open the build and inspect its console output and archived JSON reports. A failed stage stops later stages; available reports remain attached to that build.

Builds run one at a time and have a 30-minute timeout. Jenkins keeps the latest ten builds. Avoid editing deployment inputs while a build is planning or applying: changed source invalidates the saved-plan review and requires a fresh build.

## What the stages do

| Stage | Behavior |
|---|---|
| Application and guard tests | Runs Python backend/agent/policy tests, frontend Node tests, AWS adapter tests, and Python compilation checks. |
| Docker build and loopback health | Builds a uniquely tagged image, starts its own temporary container on an automatically assigned `127.0.0.1` port, and checks `/api/health`. Cleanup targets only that build's container and image. |
| AWS target and Terraform validation | Verifies the configured AWS account, Sydney region (`ap-southeast-2`), and active AWS Free plan. Initializes Terraform with the existing provider lockfile, then checks formatting and validation. |
| Plan and review | Saves a Terraform plan privately and rejects resource creation, deletion, replacement, permission changes, and unapproved configuration changes. Refresh-only drift is handled separately as described below. |
| Apply reviewed saved plan | Runs only when **DEPLOY_AWS** is selected. Applies the exact reviewed plan after checking its account, region, age, file hash, and source fingerprints. |
| Cloud smoke checks | Checks the website/security headers, cloud configuration, JavaScript, unauthenticated API rejection, dashboard CORS, and private S3 access. A temporary Cognito user verifies login and protected fleet reads. Release checks compare reported release metadata, deployed frontend hashes, both Lambda code hashes, and fleet integrity. The helper removes the temporary user afterward. |

The deployment allowance covers code updates to the **existing** API/worker Lambda functions and byte changes to **existing** frontend S3 objects. Adding a frontend object, changing IAM, or creating infrastructure needs a separate review; the job deliberately rejects those plans. Saved plans expire after one hour. A successful no-change apply does not create resources.

Terraform can omit an unchanged caller-identity data source from `planned_values`. The account check may use the plan's refreshed `prior_state` only when the planned identity is omitted and no identity read/change is pending. It never accepts an old identity in place of a deferred read.

The review report's `refreshOnlyDrift` lists refreshed managed resources only when each has a matching proposed managed-resource `no-op`. Those entries are informational; all proposed mutations still pass the code-only restrictions. This policy restricts planned changes and does not claim to audit every kind of remote drift.

Cloud smoke checks leave fleet telemetry unchanged. Creating and cleaning up the temporary authentication-test user is an account-side change, so that helper is not entirely read-only.

## Release and rollback evidence

Build #5 proved an actual code release after build #4's successful zero-change apply. All 13 served frontend assets and both Lambda ZIP hashes matched the release checkpoint. The live browser showed UI/API **0.3.0**, three healthy devices, 45 readings, and one duplicate. The persisted fleet payload hash and revision **16** were unchanged. See the packaged [release screenshot](../evidence/edgeops-release-0.3.0.jpg).

The rollback restored the exact 33-file baseline snapshot and successfully deployed it through build #6. The already-loaded 0.3.0 browser correctly displayed **API unknown** when the baseline API returned no release metadata, instead of claiming a version match. Fleet revision remained **16**. See the packaged [rollback-detection screenshot](../evidence/edgeops-rollback-detection.jpg).

Build #8 restored the exact 34-file 0.3.0 source checkpoint and deployed it successfully. The aggregate verification compared all 13 frontend hashes against immutable manifests, verified both Lambda hashes, confirmed that rollback restored the original build #4 Lambda package, and confirmed that builds #5 and #8 deployed identical 0.3.0 packages. Fleet payload SHA-256 and revision **16** were identical across all three successful runs.

| Run | Result | Duration | Tests | AWS updates |
|---|---|---:|---:|---:|
| #5: deploy 0.3.0 | SUCCESS | 211.9 s | 105 | 7 |
| #6: restore original baseline | SUCCESS | 222.3 s | 99 | 7 |
| #8: restore 0.3.0 | SUCCESS | 177.5 s | 105 | 7 |

This is source-snapshot restoration followed by the normal reviewed-plan deployment; it does not destroy infrastructure, switch Lambda aliases, or roll back the database. The rehearsal-only fleet comparison baseline has been archived, so future builds are not pinned to revision 16 while ordinary telemetry changes. See the packaged [restored release](../evidence/edgeops-release-restored.jpg) and [successful Jenkins run](../evidence/edgeops-jenkins-release-success.jpg).

## Private state and reports

The controller uses the persistent `outputs/edgeops` workspace instead of a disposable checkout. It depends on the existing `infra/terraform.tfstate`, `infra/terraform.tfvars`, and `.terraform.lock.hcl`, plus the AWS/Terraform credential wrappers in the parent workspace's `work/` directory.

A local helper outside this repository (`work/start_jenkins.py`) starts Jenkins with the `EDGEOPS_*` runtime paths, expected account, region, and helper configuration. `scripts/pipeline.py` executes stages; `scripts/pipeline_policy.py` validates plans and source fingerprints. The authenticated check uses `work/cloud_readiness.py`, which invokes `work/release_verification.py` for deployed release/artifact checks and records their hashes in the sanitized archived report.

Jenkins also needs the non-secret `EDGEOPS_*` paths and target settings in **Manage Jenkins → System → Global properties → Environment variables** (`EnvironmentVariablesNodeProperty` in the global node properties). Setting them only in the controller's operating-system process environment is insufficient for this setup: Declarative Pipeline evaluates `customWorkspace` before it enters the agent. In particular, `EDGEOPS_PROJECT_DIR` must resolve at that point. Keep actual credentials in the private helpers, not in these global variables.

The first attempted build stopped with `workspace: null` before tests or AWS actions because that global configuration was absent. Setting the global environment corrected the configuration; the Jenkinsfile did not need a code fix. Build #2 passed tests, Docker, and Terraform validation but stopped before apply because the original guard did not handle Terraform 1.9.8's unchanged identity/refresh representation. The corrected policy has 28 guard tests, including regressions for those cases.

Build #3 executed the reviewed zero-change apply and passed public cloud checks. Its last helper stopped on a `PermissionError` importing `boto3` in the Jenkins process. The SDK directory was readable by the setup context but lacked read/execute access for the native Windows account running Jenkins. The failure occurred before temporary-user creation and did not mutate the fleet. Read/execute access was then granted on the SDK files only; pipeline source and deployment guards were unchanged. A focused check in the Jenkins context passed, followed by the complete successful build #4.

- Sanitized stage summaries are written to `reports/pipeline/<BUILD_TAG>/` and archived by Jenkins.
- Saved plans, review manifests, and private command diagnostics stay under `artifacts/pipeline-private/<BUILD_TAG>/` and are not archived by the job.
- Keep Terraform state, plan files, credential-helper material, and the private Jenkins home out of shared archives and screenshots. A Terraform plan or state file can contain sensitive values even when its console summary looks harmless.

The exportable project alone is **not a self-contained Jenkins installation**. These Windows `bat` stages rely on this machine's runtime, private wrappers, persistent state, and configured worker label `edgeops-windows`. Moving to another machine requires recreating those dependencies and securely transferring or re-establishing state and credentials.

## Controller operation and limits

The installed controller is Jenkins **2.580.1** with Java **21.0.12.1**. Its runtime is under `work/jenkins-runtime`; its private home is `work/jenkins-home`. Setup installed 51 official, checksum-verified plugins for the Pipeline dependencies.

Jenkins is a manually started local process, not a Windows service or an automatically started server. Restart it using the workspace launcher when needed, and keep it bound to loopback. Docker Desktop must also be available for container checks. A machine restart does not imply that this controller has restarted.

This is a portfolio/demo controller with one persistent workspace. Jenkins/plugin security updates, backups, credential renewal, and controller startup are manual responsibilities. It is not a production high-availability CI service. The active Free-plan check does not impose a hard spending cap or guarantee free AWS usage.
