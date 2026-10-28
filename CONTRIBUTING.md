# Contributing

Thanks for taking a look. EdgeOps is a portfolio project, but issues and pull requests are welcome.

## Setup
- Python 3.11+ (standard library only) and Node.js 20+ for the frontend tests
- Terraform 1.17.0 only if you change `infra/`
- No API keys or cloud account are needed for local work

```sh
python3 -m backend.server --port 8765 --data data/edgeops.sqlite3   # http://127.0.0.1:8765
```

## Checks (run before every pull request)
```sh
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s infra/tests -v
node --test frontend/tests/*.test.mjs
terraform -chdir=infra fmt -check && terraform -chdir=infra init -backend=false && terraform -chdir=infra validate
```
CI runs the same checks plus a Docker build and health check.

## Pull requests
1. Branch from `main`; keep each PR to one change.
2. Add or update tests for behaviour changes.
3. Update the matching doc in `docs/` (and an ADR in `docs/decisions/` for a design change).
4. Add a line under **Unreleased** in [CHANGELOG.md](CHANGELOG.md).
5. `main` is protected: changes land through a PR with green CI.

## Never commit
- Credentials, tokens, AWS account IDs, `*.tfstate`, `*.tfvars`, `.env` files
- `data/` (local SQLite), local pipeline `reports/` output, or machine-specific paths
- Non-synthetic device or user data

## Code style
- Keep domain logic free of HTTP and storage imports (see [ADR 0003](docs/decisions/0003-stdlib-local-mode.md)).
- No new runtime dependencies without discussion.
- Bind servers to loopback.
