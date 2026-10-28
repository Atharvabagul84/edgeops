# 0002: Code-only release policy

**Status:** Accepted

## Context
Releases run from a pipeline with AWS credentials. A mistaken plan could create, delete or re-permission resources in a live account.

## Decision
The Jenkins pipeline saves a Terraform plan and `scripts/pipeline_policy.py` rejects it unless it is complete, targets the expected account and Region, and only updates existing Lambda code and frontend objects. Resource creation, deletion and permission changes fail plan review. Apply runs only the reviewed saved plan, and only with `DEPLOY_AWS` approved. Smoke checks then compare deployed artifact hashes.

## Consequences
- Releases and rollbacks are safe to repeat; the rehearsal (builds #5, #6, #8) matched every hash.
- Infrastructure changes need a separate, deliberate Terraform run outside the pipeline.
- Rollback restores code, not DynamoDB data.
