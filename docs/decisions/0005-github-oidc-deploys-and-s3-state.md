# 0005: GitHub Actions OIDC deploys with S3 state and native locking

**Status:** Accepted (2026-10-31). The Jenkins pipeline (ADR 0002) stays as an optional legacy path.

## Context
v1.0.0 released through a Jenkins controller on the owner's Windows PC, with Terraform state on that disk. Nobody else could reproduce a deploy. The live run also used a broad role. A deploy role that can create Lambda roles can also escalate: it could write an admin policy onto a role it creates, then pass that role to a function.

## Decision
- **State** lives in an S3 bucket created by `infra/bootstrap`. Versioning, SSE-S3, public access block, TLS-only, and a bucket policy that denies everyone except the two deploy roles and named admins. Locking uses Terraform's native S3 lock file (`use_lockfile = true`, Terraform 1.10 or later), not a DynamoDB lock table: there's one fewer resource to pay for and secure, and DynamoDB locking is deprecated in the S3 backend.
- **Two OIDC roles, separated by the `sub` claim** (exact `StringEquals`, no wildcards):
  - `edgeops-github-plan`: `repo:<owner>/<repo>:pull_request`. Read-only, plus write access to the state's `.tflock` object only.
  - `edgeops-github-apply`: `repo:<owner>/<repo>:environment:production`. Only jobs in the protected environment (required reviewer, `main` only) get this `sub`.
- **Escalation guard on the apply role:**
  - `iam:CreateRole`, `PutRolePolicy` and `AttachRolePolicy` are allowed only when `iam:PermissionsBoundary` equals the workload boundary. The boundary caps any created role at the Lambda runtime's needs: its own logs, the fleet table's items and the telemetry queues.
  - `iam:PassRole` is limited to the two Lambda role ARNs, and only to `lambda.amazonaws.com`.
  - Explicit denies: removing the boundary, editing policy versions, creating users or keys, touching `edgeops-github-*` roles, Cognito `Admin*` and `SignUp`, and weakening the state bucket.
- **Repository identity** is the `owner/name` variable `github_repository`. No numeric repository ID is hard-coded, so a fork deploys to its own account by setting its own variables.
- **Checks:** Checkov runs on the Terraform source in CI and on the plan JSON before apply. Plan JSON is never uploaded as an artifact, because it holds resource attributes.

## Consequences
- "What stops a malicious PR from creating an admin role?" A PR token can't assume the apply role: the trust `sub` doesn't match. The PR workflow asserts this against real STS on every run, and `infra/tests/test_deploy_policies.py` checks it offline. A reviewed apply can only create roles that carry the boundary, so even a merged bad change gets no more than the boundary allows.
- The plan role still has broad read access (`Describe`/`Get`/`List`) for refresh. Any same-repository PR can use it. It can't change resources.
- The bootstrap root uses the owner's admin credentials once and keeps its state locally (outside git). This is the usual chicken-and-egg for remote state.
- The first plan may hit an `AccessDenied` for a read action Terraform needs that isn't listed. Add that action to `deploy-read.json.tpl`. Never widen to `*`.
- Jenkins can't run against S3 state without changes, because `scripts/pipeline.py` expects a local `terraform.tfstate`. It stays documented as the v1.0.0 release path.
