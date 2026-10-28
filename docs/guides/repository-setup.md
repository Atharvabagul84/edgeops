# Fresh-clone setup

This private repository contains the EdgeOps application source, tests, Terraform configuration, Jenkinsfile, dependency locks and historical sanitized verification evidence.

## Local application

Use Python 3.11+ (verified with 3.12.14). No Python package installation is needed for the local server; the frontend uses plain HTML/CSS/JavaScript.

    python -m backend.server --port 8765 --data data/edgeops.sqlite3

Open `http://127.0.0.1:8765`. The initial fleet is synthetic and the new database belongs to this clone. The start.cmd launcher is also available on Windows.

## Tests

Use Node 20+ for frontend tests (verified with 24.19.0), alongside Python:

    python -m unittest discover -s tests -v
    node --test frontend/tests/*.test.mjs
    python -m unittest discover -s infra/tests -v

The released source passed 105 tests: 62 backend/agent/pipeline, 21 frontend and 22 mocked AWS adapter tests. The last portability verification repeated these in a clean Linux container and a fresh isolated Windows Jenkins controller. Those are historical checks, not GitHub Actions results.

## Locked cloud and CI dependencies

The local app itself needs no SDK. For tools that operate AWS, install the seven pinned SDK packages into a fresh environment:

    python -m venv .venv
    .venv/Scripts/python.exe -m pip install --require-hashes -r dependencies/requirements-cloud.lock

On Linux/macOS the virtual-environment executable is .venv/bin/python. This repository install downloads verified package bytes; the separate local migration ZIP contains offline wheels.

dependencies/runtime-lock.json records exact Windows runtime artifacts and hashes. dependencies/plugins.lock and plugins-manifest.json pin 51 Jenkins plugins; infra/.terraform.lock.hcl locks providers. dependencies/docker-images.lock.json records the images used for the portability rehearsal. The application Dockerfile is the original release file and has not been rewritten to match those separate rehearsal recipes.

The exact Python 3.12.14 Windows distribution used originally is not available as an official Python.org binary; the pinned container supplies that exact Python version. A compatible native Python is an explicit prerequisite. Jenkins/Java, Docker Desktop, AWS CLI and Terraform installations remain separate from a Git clone.

## Existing deployment and CI

The recorded existing AWS deployment is in ap-southeast-2. The reusable Terraform source defaults to another Region, so never apply this clone to the existing deployment without its explicit Sydney override, authoritative private state and fresh authentication. Do not initialize empty state as a substitute for recovering the existing stack.

Jenkinsfile uses Windows bat stages and configured EDGEOPS_* runtime/helper paths. The original CI uses a persistent workspace, not automatic SCM checkout. Even DEPLOY_AWS=false performs AWS identity, plan and cloud checks. Creating this GitHub repository neither changes that pipeline nor deploys anything.

The private migration ZIP on the original computer includes configurable workspace setup, helper source, encrypted-state transfer instructions and detailed rehearsal evidence. It intentionally remains separate from this app repository. To move full CI/cloud operations, use that kit and transfer private state through its documented separate process.

## Repository scope

Credentials, live Terraform state/variables/plans, databases, Jenkins home, personal CV, chat history and the complete session archive are excluded. Historical sanitized reports and screenshots remain because the project documentation links to them. GitHub visibility is private; do not change it without reviewing documentation and account/resource identifiers for public release.
