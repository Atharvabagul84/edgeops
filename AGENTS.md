# Agent Instructions

## 01 Purpose
EdgeOps is a fleet-reliability demo: a durable device outbox, idempotent replay and duplicate suppression, and an incidents dashboard. It runs locally (Python stdlib + SQLite) and is **deployed live on AWS** (ap-southeast-2) with Terraform and a guarded Jenkins pipeline. Treat the AWS stack as production: real account, real credit, shared demo data.

## 02 Before You Start
- Read docs/HANDOFF.md first (local only, never commit it)
- Read README.md and docs/README.md (index), then the doc for your task in docs/guides/ or docs/reference/. Record design changes as an ADR in docs/decisions/
- Domain logic is separate from HTTP and persistence; the AWS adapter reuses it unchanged. Keep it that way

## 03 Live infrastructure rules (never break these)
- **Never** run `terraform apply`, `terraform destroy`, `terraform import`, `terraform state` changes, or any AWS CLI command that creates, updates or deletes resources or data, without the owner's explicit OK in chat for that exact command
- Read-only AWS commands (`describe`, `get`, `list`, `sts get-caller-identity`) are fine, but say which profile and Region you use
- Releases go only through the guarded Jenkins pipeline (plan review rejects anything except code-only updates). Don't apply plans by hand
- Terraform state and the saved teardown plan live outside the repo (`outputs/`). Never move, copy, print or commit them
- Never print, export or paste AWS credentials, Cognito passwords or tokens. Don't run `aws configure export-credentials` to display values
- Don't create Cognito users or change project access policies
- Dashboard actions on the deployed app change the shared fleet. Ask before running demos against the cloud
- Stay within free usage and the existing credit. No new paid services

## 04 General Rules
- Python 3.11+ standard library for the backend; no new dependencies without asking
- Frontend is plain JS tested with `node --test`; no framework
- Keep all demo data synthetic. No uptime, multi-tenancy or production-load claims
- Bind local servers to loopback
- Update docs/reference/validation.md when you verify something live, and keep "not yet verified" items honest
- Stage files by name; never commit docs/HANDOFF.md, `data/`, new local `reports/` output (the recorded `reports/pipeline/` evidence is tracked on purpose) or any tfvars

## 05 Useful Commands
```
python3 -m backend.server --port 8765 --data data/edgeops.sqlite3   # local app
python3 -m unittest discover -s tests -v                            # backend + agent
node --test frontend/tests/*.test.mjs                               # frontend
python3 -m unittest discover -s infra/tests -v                      # AWS adapter
terraform -chdir=infra fmt -check && terraform -chdir=infra validate   # read-only checks
```

## 06 When Unsure
- Check docs/ first, then ask. For anything that touches AWS, ask before acting
