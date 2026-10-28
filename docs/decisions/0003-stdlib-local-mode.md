# 0003: Standard-library local mode

**Status:** Accepted

## Context
Reviewers should be able to run the whole system in a minute, with no account, API key or package install, and the cloud version should not fork the business logic.

## Decision
The backend uses only the Python 3.11+ standard library: `http.server` on loopback and SQLite. Domain logic lives in modules with no HTTP or storage imports, and the AWS Lambda adapter calls the same functions.

## Consequences
- `python3 -m backend.server` runs everything offline; the tests run with no dependencies.
- Local processing is synchronous; local counters don't claim SQS or CloudWatch behaviour.
- The local server is a lab tool: it binds to loopback and must not be exposed publicly.
