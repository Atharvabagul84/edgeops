# Security policy

## Supported versions
Only the latest release on `main` is supported.

## Reporting a vulnerability
Please **don't open a public issue**. Use GitHub's [private vulnerability reporting](https://github.com/Atharvabagul84/edgeops/security/advisories/new) instead. Include what you found, how to reproduce it, and the impact you expect. You'll get a reply within 7 days.

## Scope
- The application code, Terraform, the release pipeline and its policy checks are in scope.
- The deployed demo uses synthetic data and admin-created accounts only. Please don't attempt to access accounts that aren't yours, run load tests, or try to exhaust the AWS account.

## Handling secrets
- No credentials, account IDs, Terraform state or tfvars belong in this repository. Secret scanning and push protection are enabled.
- AWS access uses short-lived CLI login sessions; Cognito passwords and tokens are never written to storage or logs.
