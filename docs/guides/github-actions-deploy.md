# GitHub Actions deploy (OIDC, S3 state)

[`deploy.yml`](../../.github/workflows/deploy.yml) plans on pull requests and applies from `main` in the protected `production` environment. The design and its threat model are in [ADR 0005](../decisions/0005-github-oidc-deploys-and-s3-state.md). Jenkins ([CI pipeline](../reference/ci-pipeline.md)) remains the v1.0.0 path and isn't needed.

Every step below changes a live AWS account or GitHub settings. The owner runs them; they are not part of CI.

## 1. Bootstrap (once, with admin credentials)

```bash
cd infra/bootstrap
terraform init
terraform apply -var='state_admin_principal_arns=["<your admin role or SSO role ARN, wildcards allowed>"]'
```

The bootstrap creates the state bucket, the GitHub OIDC provider (`-var=create_oidc_provider=false` if one already exists), the `edgeops-demo-workload-boundary` policy and the `edgeops-github-plan` / `edgeops-github-apply` roles. A fork sets `-var=github_repository=<owner>/<repo>`. Keep the bootstrap's local state outside git (it's ignored). Commit the generated `infra/bootstrap/.terraform.lock.hcl`.

## 2. Move the main stack's state to S3

```bash
cp infra/backend.hcl.example infra/backend.hcl   # fill in the bucket from the bootstrap outputs
terraform -chdir=infra init -migrate-state -backend-config=backend.hcl
```

Terraform copies the local `terraform.tfstate` into the bucket. Keep the old local file as a backup until the first remote plan shows no unexpected changes.

## 3. GitHub settings

- **Environment `production`:** required reviewer = you, deployment branches = `main` only, optionally "Prevent self-review" off (you're the only reviewer).
- **Repository variables** (Settings → Secrets and variables → Actions → Variables; none of these are secrets):

| Variable | Value |
|---|---|
| `AWS_ACCOUNT_ID` | 12-digit account ID |
| `AWS_REGION` | `ap-southeast-2` |
| `AWS_PLAN_ROLE_ARN` | bootstrap output `plan_role_arn` |
| `AWS_APPLY_ROLE_ARN` | bootstrap output `apply_role_arn` |
| `TF_STATE_BUCKET` | bootstrap output `state_bucket` |
| `PERMISSIONS_BOUNDARY_ARN` | bootstrap output `permissions_boundary_arn` |
| `ALARM_EMAIL` | optional |

Until `AWS_PLAN_ROLE_ARN` / `AWS_APPLY_ROLE_ARN` are set, both deploy jobs are skipped.

## 4. What a run does

- **Pull request:** tries to assume the apply role with the PR's token and fails the job if that works; assumes the plan role; `terraform plan`; posts a summary (action counts, whether the plan passes the legacy code-only policy); runs Checkov on the plan JSON.
- **Push to `main` / manual run:** waits for the environment approval, then runs the tests, assumes the apply role, plans again, refuses deletes or replacements (unless run manually with `allow_delete`), runs Checkov, applies the saved plan and checks that the website responds.

## 5. First apply of the per-device data model

Expected plan: create `aws_dynamodb_table.fleet`; update the two Lambda roles (boundary), their inline policies, the Lambda environment (`FLEET_TABLE`) and the throttle alarm; forget `aws_dynamodb_table.state` (`removed`, not destroyed). The new table starts empty, and the first command seeds the synthetic fleet.

After you've checked the new release, delete the v1.0.0 table by hand:

```bash
aws dynamodb delete-table --table-name edgeops-demo-state --region ap-southeast-2
```

Until then you can roll back by redeploying v1.0.0, which still reads that table.

## Troubleshooting

- `AccessDenied` during plan or apply: the role lacks one action Terraform needs. Add exactly that action to `infra/bootstrap/policies/*.json.tpl`, re-apply the bootstrap, and rerun. Don't widen to `*`.
- `Error acquiring the state lock`: another run holds `terraform.tfstate.tflock`. Wait for it; `terraform force-unlock` only if that run is dead.
