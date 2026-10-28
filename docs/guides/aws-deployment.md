# AWS deployment and operations

**The AWS stack was deployed on 6 October 2026 in Sydney (`ap-southeast-2`): Terraform added 51 resources.** Twelve live API/Cognito/SQS checks, six public cloud checks, the user's authenticated browser recovery demonstration and a saved cloud export passed. The post-deployment Terraform plan reported no changes.

Open [EdgeOps on AWS](https://d3aum9pitkz6he.cloudfront.net). Its API base URL is `https://example123.execute-api.ap-southeast-2.amazonaws.com`; application routes require Cognito authentication. This directory contains the deployed Terraform infrastructure and an AWS transport adapter sharing the local business logic. The frontend reads cloud configuration, signs operators into Cognito, handles the first-login password challenge, and sends authorized requests to the configured API. Without cloud configuration, it retains same-origin local operation. Real-account acceptance results are tracked in [VALIDATION.md](../reference/validation.md).

Account status verified in the AWS console and account API on 6 October 2026: the new **AWS Projects** account is active, with the EdgeOps project in **Asia Pacific (Sydney), `ap-southeast-2`**. The initial available credit was **$100**; a later account API check on the same date confirmed **$120 available on the active Free plan**, with a plan end date of **6 April 2027**. Credit exhaustion can end it earlier. The private local `infra/terraform.tfvars` records the observed Region. Temporary project credentials successfully provisioned the stack, and the core live API/queue checks passed. The instructions below account for this sign-up flow.

## What is deployed

- An HTTP API with Cognito JWT authorization on every application route.
- Admin-created operator accounts only; no public signup or browser client secret.
- Separate API and worker Lambda functions and narrowly scoped IAM roles, running Python 3.12 on ARM64.
- A standard SQS telemetry queue, partial batch failures, five attempts before a dead-letter queue, and 180-second visibility timeout for a 25-second function.
- A DynamoDB table holding a bounded, single-tenant demonstration state. Conditional version writes retry conflicts against the latest state.
- A private, encrypted S3 frontend bucket behind CloudFront Origin Access Control and HTTPS, with a Content Security Policy allowing scripts from the site itself and connections to regional API Gateway/Cognito endpoints.
- Three-day API/Lambda logs and two operational alarms for dead letters and DynamoDB write throttling. Both alarms currently have no notification actions configured. The optional Terraform email subscription would require recipient confirmation; the separate cost-budget alerts below are already configured.

No NAT gateway, VPC, EKS, load balancer, RDS, IoT Core or AI service is provisioned. Devices in this MVP are synthetic. The telemetry API uses operator authentication; it is not device-certificate authentication.

## Local verification

From the EdgeOps project folder:

```powershell
python -m unittest discover -s infra/tests -v
terraform -chdir=infra init -backend=false
terraform -chdir=infra fmt -check
terraform -chdir=infra validate
```

The 20 adapter tests pass using deterministic AWS API fakes and shared domain logic. They cover conditional-write retry, persistence failure, state size bounds, authentication rejection, queue acceptance, partial batch failures, reset/tick aliases, export metadata, content type, body size, nesting, non-finite JSON numbers, base64 decoding, rejecting malformed bodies before database access, and rejecting invalid telemetry batches before queueing. These tests do not validate real IAM enforcement, JWT verification by API Gateway, AWS service integration or deployed performance. Terraform init installs providers; it does not create AWS infrastructure.

Verification on 6 October 2026: normal `terraform init -input=false -no-color` completed with Terraform 1.9.8, AWS provider 6.67.0 and archive provider 2.8.1. Terraform verified both providers as signed by HashiCorp and generated `infra/.terraform.lock.hcl`. Windows temporary-file access required an approved sandbox exception for installation. Subsequent `terraform fmt -check` and provider-backed `terraform validate -no-color` passed with the normally installed providers, without development overrides. These initial checks used no AWS account APIs. A subsequent authenticated plan and apply created the deployment described above; no cloud benchmark is claimed.

## How the cloud connection works

1. The browser fetches `/cloud-config.json` using `cache: "no-store"`. Terraform uploads `mode`, `apiBaseUrl`, `region`, `userPoolId`, and `clientId`; these are public identifiers, not secrets. Missing configuration selects local mode; invalid configuration fails closed.
2. The operator form uses Cognito `InitiateAuth` with `USER_PASSWORD_AUTH`, the public client ID, and supplied credentials. Admin-created users complete `NEW_PASSWORD_REQUIRED` through `RespondToAuthChallenge`. The pool disallows public registration and requires passwords with at least 12 characters including uppercase, lowercase, a number, and a symbol. Temporary passwords expire after one day. Tokens and passwords are not written to browser storage, source code or Terraform state. Browser sessions remain in memory; reloading requires sign-in.
3. API requests use `apiBaseUrl` and `Authorization: Bearer <ID token>`. The HTTP API authorizer checks the Cognito issuer and client audience. Route scopes are deliberately not configured, matching Cognito ID-token authentication for this small operator application. Cognito refresh tokens renew sessions in memory; cleared/expired sessions require sign-in before polling or actions resume.
4. CloudFront serves static assets; `/api/*` requests go directly to the configured API URL. CORS permits only the deployed CloudFront origin. Local operation continues without cloud configuration.
5. In cloud mode, POST `/api/telemetry` is asynchronous and returns HTTP 202 with `accepted` and `messageId`. Poll state to observe completed processing. Local ingestion remains synchronous.
6. Cloud simulator ticks are manual and cloud state polling is 30 seconds apart. There is no scheduler or always-running cloud simulator. After the first cloud sign-in, use Reset demo once to persist the initial synthetic fleet; before the first action, an empty table returns an initial sample without saving it.

API routes: `GET /api/health`, `GET /api/state`, `GET /api/export`, `POST /api/actions`, `POST /api/tick`, `POST /api/reset`, `POST /api/telemetry`. Export returns public state plus `exportedAt`, `diagnosticNote`, and an attachment filename. Actions and telemetry input payloads match the local API; the asynchronous telemetry response is the intentional cloud difference. POST bodies require `application/json`, finite numbers, at most 64 KiB and nesting no deeper than 16 levels. Invalid telemetry receives 400 before any SQS message is sent; the worker validates it again before writing state.

## Account preparation and deployment sequence

### New AWS Projects account: the current account

Activation is complete for the EdgeOps project, and the console confirms **`ap-southeast-2`**. For any other account, open **AWS Settings → Project → Overview → Additional Info** and record the actual Region and account ID. In this experience, AWS assigns a Region from `us-east-2`, `eu-north-1`, or `ap-southeast-2`; do not infer it from your location. Regional resources must use that assigned Region. The reusable Terraform default remains `ap-south-1`; this account's private local `infra/terraform.tfvars` explicitly overrides it with `ap-southeast-2`. Preserve that override before planning. [AWS project Regions](https://docs.aws.amazon.com/accounts/latest/reference/project-regions.html)

The new experience manages human access through projects and teams and does not create a root user. Use the existing project administrator session; creating a separate IAM console administrator or setting up root MFA is not a prerequisite for this account type. IAM users and roles can be created for programmatic access, including the Lambda execution roles managed by this project. Account activation, identity/payment verification and acceptance of AWS terms remain account-owner steps. [Compare AWS sign-up options](https://docs.aws.amazon.com/accounts/latest/reference/sign-up-for-aws.html)

For a **classic/advanced AWS account**, the guidance is different: secure the root user with MFA, avoid root access keys, and deploy with an appropriately authorized temporary operator identity. Do not apply those root-user steps to the managed Projects flow above.

### Sign in with temporary CLI credentials

Install AWS CLI v2.32.0 or later and Terraform. The new Projects experience supports `aws login`: choose the existing browser session for the intended project and use its assigned Region. AWS deployment credentials are separate from the Cognito operator account used to log into the EdgeOps dashboard after deployment. [Project CLI access](https://docs.aws.amazon.com/accounts/latest/reference/connect-ai-coding-tool.html), [AWS CLI browser login](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html)

```powershell
# Observed Region for the EdgeOps project; re-check AWS Settings for another account.
$edgeRegion = 'ap-southeast-2'
aws configure set region $edgeRegion --profile edgeops-login
aws login --profile edgeops-login --region $edgeRegion

# Read-only checks: confirm the intended account, active Free plan/credits and quota.
aws sts get-caller-identity --profile edgeops-login
aws freetier get-account-plan-state --profile edgeops-login --region $edgeRegion
aws lambda get-account-settings --profile edgeops-login --region $edgeRegion --query AccountLimit
```

If the browser cannot select the expected project session, first check the CLI Region against AWS Settings. Add `--remote` to the same named-profile login command when a local browser callback cannot be used. For classic IAM/federated identities, AWS documents the `SignInLocalDevelopmentAccess` managed policy as a login prerequisite; it does not grant permission to create this stack. Do not change project access policies merely because a classic-account tutorial recommends it. [Login troubleshooting](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in-troubleshoot.html)

Some SDK versions and infrastructure tools cannot consume the CLI's `login_session` configuration directly. AWS documents a `credential_process` bridge for this case. Add a separate profile to the AWS config file in use (`%USERPROFILE%\.aws\config`, or the file selected by `AWS_CONFIG_FILE`), using the same observed Region:

```ini
[profile edgeops-deploy]
region = ap-southeast-2
credential_process = aws configure export-credentials --profile edgeops-login --format process
```

Keep the CLI executable on PATH, or use its quoted absolute path in `credential_process`. This profile lets Terraform request temporary credentials from the signed-in profile without manually copying keys. Do not run the export command merely to display or paste credentials. Login sessions last up to 12 hours; repeat `aws login --profile edgeops-login --region <project-region>` when required. [AWS credential-process bridge](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html)

### Plan and deploy after the checks succeed

The current workspace has already completed the deployment. The commands in this section document reproduction and future updates; preserve the existing Terraform state when operating this stack. This computer's existing deployment uses the workspace helpers and isolated profiles documented under Removal below, rather than the alternative manual profile names in these setup examples.

This account's private local `infra/terraform.tfvars` has been prepared with the **actual observed project Region**. When using another account, edit this value only after checking its Region, preserving any other settings:

```hcl
region = "ap-southeast-2"
```

Keep this override for later plans and removal. Confirm the CLI account ID matches AWS Settings and the Free plan is active with available credits before continuing. New accounts may have reduced Lambda quotas. The worker mapping caps concurrency at two; no function reserves concurrency, so the rule requiring 100 unreserved executions does not impose a separate reservation prerequisite. [Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html), [SQS concurrency](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-scaling.html)

```powershell
# From the EdgeOps project folder, using the credential-process profile above:
$env:AWS_PROFILE = 'edgeops-deploy'
aws sts get-caller-identity
terraform -chdir=infra init
terraform -chdir=infra validate
terraform -chdir=infra plan -out=deployment.tfplan
# Review the complete proposed resources and costs before running this:
terraform -chdir=infra apply deployment.tfplan
terraform -chdir=infra output
```

Regional prices and account quotas differ. Set `alarm_email` only to your own desired recipient; applying it sends a subscription confirmation. With the default empty value, alarms appear in CloudWatch without email delivery.

The user has created a personal Cognito operator and successfully signed in to the deployed dashboard. Additional operators can be created in the Cognito console. All permitted operators share the same fleet and can reset the demonstration. Do not add untrusted users. CloudWatch alarms are visibility tools and are not spending limits.

As checked on 6 October 2026, the new Projects Free plan explicitly supports this stack's Cognito, API Gateway, Lambda, SQS, DynamoDB, S3, CloudFront and CloudWatch services. This architecture uses none of its excluded cross-Region features or Lambda@Edge. A paid-plan upgrade is not required simply to use these services. Actual activation, permissions, quotas and credits still need account checks. [Supported Free-plan services](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html)

AWS advertises $100 initial credits with up to $100 more through eligible activities. The Free plan ends after six months or credit exhaustion, whichever occurs first; Free-plan usage beyond always-free allowances consumes credits. On expiration, access to resources is lost unless the account is upgraded, with a limited recovery period. This is not a promise of permanent free hosting or zero metered usage. Do not upgrade to a paid plan merely to complete this demo; upgrading changes the billing boundary. Check actual credits and expiration using `get-account-plan-state` and AWS Settings. [AWS Free Tier terms and FAQs](https://aws.amazon.com/free/free-tier-faqs/), [Account plan state](https://docs.aws.amazon.com/cli/latest/reference/freetier/get-account-plan-state.html)

## Authenticate the standalone agent

First complete the operator's temporary-password change in the deployed dashboard. The CLI agent does not obtain or refresh tokens itself. This PowerShell workflow prompts privately for the existing Cognito credentials and keeps the ID token only in process memory. It has been prepared but not executed against AWS:

```powershell
# From the EdgeOps project folder after successful deployment:
. .\scripts\runtime.ps1
$edgePython = Get-EdgeOpsPython
$edgeWebsite = terraform -chdir=infra output -raw website_url
$edgeConfig = Invoke-RestMethod -Uri ($edgeWebsite.TrimEnd('/') + '/cloud-config.json')
$edgeCredential = Get-Credential -Message 'Cognito operator email and current password'
try {
    $edgeBody = @{
        AuthFlow = 'USER_PASSWORD_AUTH'
        ClientId = $edgeConfig.clientId
        AuthParameters = @{
            USERNAME = $edgeCredential.UserName
            PASSWORD = $edgeCredential.GetNetworkCredential().Password
        }
    } | ConvertTo-Json -Depth 4
    $edgeAuth = Invoke-RestMethod -Method Post `
        -Uri ('https://cognito-idp.' + $edgeConfig.region + '.amazonaws.com/') `
        -ContentType 'application/x-amz-json-1.1' `
        -Headers @{'X-Amz-Target'='AWSCognitoIdentityProviderService.InitiateAuth'} `
        -Body $edgeBody
    if (-not $edgeAuth.AuthenticationResult.IdToken) {
        throw 'Complete account setup in the dashboard first.'
    }
    $env:EDGEOPS_API_TOKEN = $edgeAuth.AuthenticationResult.IdToken
    & $edgePython scripts/device_agent.py --url $edgeConfig.apiBaseUrl --count 3
    # Repeat with --flush-only or --replay-last while the token is valid.
} finally {
    Remove-Item Env:EDGEOPS_API_TOKEN -ErrorAction SilentlyContinue
    Remove-Variable edgeBody, edgeAuth, edgeCredential -ErrorAction SilentlyContinue
}
```

A202 response means the queue accepted the batch; inspect state later to confirm worker processing. On401, authenticate again and use `--flush-only`; the unacknowledged outbox remains intact. The environment token is sent only to the configured HTTPS destination. Redirects are rejected.

## Cloud acceptance checks

Verified on 6 October 2026: no-token API requests return 401; Cognito API login and authorized state/actions succeed; reset, tick, incident acknowledgement/recovery, offline replay, deduplication and export metadata pass. Valid telemetry reached DynamoDB through SQS, and replaying the same batch suppressed duplicates. Invalid telemetry returned 400 without changing ingestion. The ephemeral test operator was deleted and the clean fleet restored. See the [sanitized smoke report](../evidence/cloud-smoke-report.json).

Public checks confirmed HTTPS site/config/script delivery, AWS/Sydney configuration, CSP/HSTS headers, and denied direct S3 access (403). An API OPTIONS preflight returned 204 with the exact CloudFront origin allowed and Authorization permitted. Chrome rendered the deployed sign-in page without console warnings or errors. The post-deployment Terraform plan returned exit code 0 with no changes.

The user then signed in with their personal operator. The authenticated Chrome dashboard showed AWS API connected, three healthy devices, 36 readings, no incidents and no duplicates. Run recovery demo completed with 45 readings, one duplicate suppressed, three buffered readings replayed, no remaining buffer and no active incidents. The authenticated export dialog opened, and the actual downloaded JSON file was found and parsed: AWS mode, synthetic-data marker, 45 ingested readings, one duplicate, three replayed readings and zero buffered readings/incidents. A copy is saved as [cloud-browser-diagnostics.json](../evidence/cloud-browser-diagnostics.json). The browser automation download event timed out, but the real downloaded file independently confirmed success. Browser console warnings/errors remained empty.

The remaining acceptance checks are:

- Observe the live first-login password challenge and an actual expired token. The user completed account setup outside the observed test; authenticated browser operation and CORS are verified, but that does not separately prove these two flows.
- Insert a deliberately malformed message into the test SQS queue using an authorized operator; confirm it reaches the DLQ after retries and the alarm changes state.
- Exercise concurrent cloud commands and confirm preserved updates or retriable failures, rather than silent overwrites.
- Inspect logs for useful identifiers and absence of credentials/request bodies.

These remaining checks are not reported as passed. No production load test or teardown has been run.

## Cost and scaling boundaries

The first account inventory on 6 October 2026 found no budgets. With the user's approval, **`edgeops-monthly-usage-usd5`** was then created and verified: a fixed **$5 monthly COST budget**, with **ACTUAL spend greater than $1 and greater than $5** email notifications to the single approved recipient, **[address redacted]**. Both notification subscriptions were read back successfully; email delivery itself has not been tested. This account-wide budget uses unblended costs and excludes credits and refunds so those adjustments do not hide underlying charges. It does not measure the exact remaining Free-plan credit balance. The initial budget actual spend returned $0.00; that value can lag usage. See [the sanitized cost readiness report](../evidence/cost-readiness.json).

AWS currently charges nothing for budget monitoring and notifications. No budget Actions or paid scheduled Reports were created. Budget data is updated up to three times daily, and charges can pass a threshold before an email arrives: **these alerts are not a spending cap and do not stop resources**. The two operational CloudWatch alarms still have no notification actions; budget emails do not subscribe the recipient to those alarms. [AWS Budgets pricing](https://aws.amazon.com/aws-cost-management/aws-budgets/pricing/), [budget update timing](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html), [cost-type settings](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_budgets_CostTypes.html)

The table provisions **5 read capacity units and 25 write capacity units**. That can fit DynamoDB's provisioned-capacity allowance when eligible and when other tables do not consume it. AWS allowances and credits are shared across applicable account/organization usage. API Gateway, Lambda, SQS, Cognito, S3, CloudFront, logs, and alarms generate metered usage subject to their current allowances. An active Free plan uses credits for eligible usage beyond those allowances without billing the customer; a Paid plan can bill usage beyond available credits. Do not assume this deployment consumes zero credits or remains free indefinitely. In particular, do not apply legacy twelve-month API Gateway or S3 offers to this new account without checking eligibility. Confirm current pricing and account plan before apply. [Free-plan billing](https://aws.amazon.com/free/free-tier-faqs/)

The state is deliberately held in one item to keep this short local-first build understandable. Measured state size ranges from about 5 KB initially to about 175 KB in a cap-loaded test. Every state change rewrites the whole item, so frequent writes can exceed the table's throughput. At the larger size, even one write consumes roughly 175 one-KB write units. Use manual, low-frequency cloud demonstrations, watch throttles, and reset after export. Do not treat the API's two-request-per-second throttle as a sustainable state-write rate.

The adapter rejects serialized states above 350,000 bytes before DynamoDB's 400-KB item ceiling. The app retains bounded histories, event IDs, incidents, and offline buffers. Deduplication is bounded; late events are discarded from current state rather than archived. Lambda retries and failed DynamoDB operations can still incur cost. Worker concurrency is capped at two; API concurrency follows account limits. Budget alerts do not impose a hard cap.

Dashboard pipeline counters are application demo counters, not live CloudWatch or SQS measurements. In particular, the domain's `deadLetters` value does not query the real queue; use CloudWatch for actual DLQ visibility and alarms.

For a production version, split device snapshots, incidents, and idempotency records into independent items; persist raw events separately, design tenant/device authorization, add recovery backups, and test throughput. There is no point-in-time recovery, archival store, multi-tenant isolation, uptime SLA, automatic DLQ redrive, fleet-certificate provisioning, or production hardening claim in this MVP.

## Removal

Export anything you want to keep first (for example the diagnostics JSON from the dashboard). Removal deletes the whole stack, including the DynamoDB fleet state.

Use the same deployment profile and Region as the deploy, and review the destroy plan before applying it:

```powershell
aws sts get-caller-identity --profile edgeops-deploy   # confirm the intended account first
terraform -chdir=infra plan -destroy -out=teardown.tfplan
terraform -chdir=infra apply teardown.tfplan
```

Terraform removes the static objects it manages before deleting their bucket. If you add objects outside Terraform, remove those explicitly after verifying the bucket identity.

An account-level AWS Budget created outside Terraform is not removed by `destroy`. Delete it separately in the Billing console (or with `aws budgets delete-budget`) once you have confirmed the account.

## Primary documentation

- [AWS Lambda: handling SQS errors and partial batch responses](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html)
- [API Gateway HTTP API JWT authorizers](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html)
- [CloudFront: restricting access to an S3 origin](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html)
- [DynamoDB provisioned capacity pricing](https://aws.amazon.com/dynamodb/pricing/provisioned/)
- [AWS Free Tier](https://aws.amazon.com/free/)

Provider dependency ranges are recorded in `versions.tf`; `infra/.terraform.lock.hcl` now records the selected versions and verified checksums. Keep that lockfile for repeatable provider selection. Provider validation is not a successful deployment.
