"""Native Windows Jenkins stages; credentials and saved plans stay private."""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

try:
    from . import pipeline_policy as policy
except ImportError:
    import pipeline_policy as policy


def clean_environment(source):
    if any(key.startswith(("TF_CLI_ARGS", "TF_VAR_")) or key == "TF_WORKSPACE" for key in source):
        raise ValueError("Inherited Terraform arguments, variables or workspace overrides are not permitted")
    env = dict(source)
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN",
                "TF_CLI_CONFIG_FILE", "TF_DATA_DIR", "TF_LOG", "TF_LOG_PATH"):
        env.pop(key, None)
    env.update(PYTHONUTF8="1", PYTHONUNBUFFERED="1", TF_IN_AUTOMATION="1")
    return env


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def fetch_url(url, method="GET", headers=None):
    request = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        response = urllib.request.build_opener(NoRedirect).open(request, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, dict(response.headers), response.read(2 * 1024 * 1024)


class Pipeline:
    def __init__(self):
        self.env = clean_environment(os.environ)
        self.project = Path(__file__).resolve().parents[1]
        if Path(self.env.get("EDGEOPS_PROJECT_DIR", "")).resolve() != self.project or Path.cwd().resolve() != self.project:
            raise ValueError("Jenkins must use EDGEOPS_PROJECT_DIR as its persistent custom workspace")
        self.python = sys.executable
        self.tf_helper = Path(self.env["EDGEOPS_TERRAFORM_HELPER"]).resolve()
        self.aws_helper = Path(self.env["EDGEOPS_AWS_HELPER"]).resolve()
        if (self.tf_helper.parent.parent / "outputs/edgeops").resolve() != self.project or self.aws_helper.parent != self.tf_helper.parent:
            raise ValueError("Deployment helpers target a different source/state workspace")
        if not self.tf_helper.is_file() or not self.aws_helper.is_file():
            raise ValueError("Configured AWS/Terraform helper is missing")
        self.account = self.env["EDGEOPS_EXPECTED_ACCOUNT_ID"]
        self.region = self.env["EDGEOPS_REGION"]
        if not re.fullmatch(r"\d{12}", self.account) or self.region != "ap-southeast-2":
            raise ValueError("Expected account and Sydney Region must be configured explicitly")
        self.run_id = self.env.get("BUILD_TAG", self.env.get("EDGEOPS_RUN_ID", ""))
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", self.run_id) or self.run_id in (".", ".."):
            raise ValueError("A safe unique BUILD_TAG or EDGEOPS_RUN_ID is required")
        self.private = self.project / "artifacts/pipeline-private" / self.run_id
        self.reports = self.project / "reports/pipeline" / self.run_id
        self.private.mkdir(parents=True, exist_ok=True)
        self.reports.mkdir(parents=True, exist_ok=True)
        self.plan_file = self.private / "deployment.tfplan"
        self.manifest_file = self.private / "review.json"
        for name in ("terraform.tfstate", "terraform.tfvars", ".terraform.lock.hcl"):
            if not (self.project / "infra" / name).is_file():
                raise ValueError("Existing deployment state, Region override and provider lockfile are required")

    def run(self, args, *, capture=True, allowed=(0,)):
        result = subprocess.run([str(arg) for arg in args], cwd=self.project, env=self.env,
                                text=True, encoding="utf-8", errors="replace", capture_output=capture)
        if allowed is not None and result.returncode not in allowed:
            if capture:
                (self.private / "last-tool-error.log").write_text((result.stdout or "") + (result.stderr or ""), encoding="utf-8")
            raise RuntimeError("Stage command failed with exit code " + str(result.returncode) + "; private diagnostic log retained")
        return result

    def tf(self, *args, allowed=(0,)):
        return self.run([self.python, self.tf_helper, *args], allowed=allowed)

    def aws_json(self, *args):
        return json.loads(self.run([self.python, self.aws_helper, *args, "--output", "json"]).stdout)

    def report(self, name, content):
        payload = {"stage": name, "run": self.run_id, "recordedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **content}
        (self.reports / (name + ".json")).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload), flush=True)

    def tests(self):
        node = self.env.get("EDGEOPS_NODE", "node")
        commands = [
            [self.python, "-m", "unittest", "discover", "-s", "tests", "-v"],
            [node, "--test", *[str(path.relative_to(self.project)) for path in sorted((self.project / "frontend/tests").glob("*.test.mjs"))]],
            [self.python, "-m", "unittest", "discover", "-s", "infra/tests", "-v"],
            [self.python, "-m", "compileall", "-q", "backend", "scripts"],
        ]
        for command in commands:
            self.run(command, capture=False)
        self.report("tests", {"passed": True, "suites": ["backend-agent-pipeline", "frontend", "aws-adapter", "python-compilation"]})

    def docker_check(self, fetch=fetch_url):
        docker = self.env.get("EDGEOPS_DOCKER", "docker")
        name = "edgeops-ci-" + uuid.uuid4().hex[:12]
        image = "edgeops-ci:" + name.removeprefix("edgeops-ci-")
        try:
            self.run([docker, "build", "--tag", image, "."], capture=False)
            self.run([docker, "run", "--detach", "--name", name, "--label", "edgeops.pipeline=true",
                      "--publish", "127.0.0.1::8765", image])
            url = policy.loopback_url(self.run([docker, "port", name, "8765/tcp"]).stdout)
            for attempt in range(30):
                try:
                    status, _, body = fetch(url + "/api/health")
                    if status == 200 and json.loads(body).get("status") == "ok":
                        self.report("docker", {"passed": True, "healthStatus": status, "binding": "127.0.0.1", "ephemeralContainer": True})
                        break
                except (urllib.error.URLError, TimeoutError, OSError):
                    pass
                if attempt == 29:
                    raise RuntimeError("Docker loopback health did not become ready")
                time.sleep(1)
        finally:
            # Unique names ensure cleanup never targets unrelated containers or images.
            cleanup = self.run([docker, "rm", "-f", name], allowed=None)
            self.run([docker, "image", "rm", image], allowed=None)
            if cleanup.returncode and "No such container" not in (cleanup.stderr or ""):
                raise RuntimeError("Could not clean up the pipeline's own Docker container")

    def identity(self):
        identity = self.aws_json("sts", "get-caller-identity")
        policy.check_identity(identity, self.account)
        return identity

    def terraform_validate(self):
        self.identity()
        plan_state = self.aws_json("freetier", "get-account-plan-state")
        if plan_state.get("accountPlanType") != "FREE" or plan_state.get("accountPlanStatus") != "ACTIVE":
            raise ValueError("The approved active AWS Free plan is not available")
        self.tf("init", "-backend=false", "-input=false", "-lockfile=readonly", "-no-color")
        self.tf("fmt", "-check")
        self.tf("validate", "-no-color")
        self.report("terraform-validation", {"passed": True, "account": self.account, "region": self.region, "accountPlan": "ACTIVE/FREE"})

    def inspect_plan(self):
        value = json.loads(self.tf("show", "-json", str(self.plan_file)).stdout)
        return policy.review_plan(value, self.account, self.region, self.project)

    def plan(self):
        self.identity()
        before = {key: value for key, value in policy.fingerprint(self.project).items() if key != "infra/.lambda.zip"}
        result = self.tf("plan", "-input=false", "-no-color", "-lock-timeout=30s", "-detailed-exitcode", "-out=" + str(self.plan_file), allowed=(0, 2))
        after = {key: value for key, value in policy.fingerprint(self.project).items() if key != "infra/.lambda.zip"}
        if before != after:
            raise ValueError("Deployment inputs changed while planning; run a new build")
        reviewed = self.inspect_plan()
        manifest = policy.make_manifest(self.project, self.plan_file, self.account, self.region)
        manifest["hasChanges"] = bool(reviewed["updates"])
        self.manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self.report("plan-review", {"passed": True, "terraformExitCode": result.returncode, **reviewed,
                                    "policy": "Existing Lambda code and frontend bytes only; no resource or permission changes"})

    def apply_deployment(self, approved=False):
        if approved is not True:
            raise ValueError("Applying requires the explicit DEPLOY_AWS job parameter")
        self.identity()
        manifest = json.loads(self.manifest_file.read_text(encoding="utf-8"))
        policy.verify_manifest(self.project, self.plan_file, manifest, self.account, self.region)
        reviewed = self.inspect_plan()
        policy.verify_manifest(self.project, self.plan_file, manifest, self.account, self.region)
        self.tf("apply", "-input=false", "-no-color", "-lock-timeout=30s", str(self.plan_file))
        self.report("apply", {"passed": True, "applyExecuted": True, "noChanges": not reviewed["updates"], "changeCount": len(reviewed["updates"]), "savedPlanOnly": True})

    def cloud_check(self):
        values = json.loads(self.tf("output", "-json").stdout)
        website = values["website_url"]["value"].rstrip("/")
        api = values["api_url"]["value"].rstrip("/")
        bucket = values["frontend_bucket"]["value"]
        if not re.fullmatch(r"https://[a-z0-9]+\.cloudfront\.net", website) or not re.fullmatch(r"https://[a-z0-9]+\.execute-api\.ap-southeast-2\.amazonaws\.com", api):
            raise ValueError("Cloud checks require the deployed CloudFront/API Gateway endpoints")
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]+", bucket):
            raise ValueError("Unexpected frontend bucket output")
        checks = []
        status, headers, _ = fetch_url(website + "/")
        headers = {key.lower(): value for key, value in headers.items()}
        checks.append({"name": "site_and_security_headers", "passed": status == 200 and bool(headers.get("content-security-policy")) and bool(headers.get("strict-transport-security"))})
        status, _, body = fetch_url(website + "/cloud-config.json")
        config = json.loads(body)
        checks.append({"name": "cloud_configuration", "passed": status == 200 and config.get("mode") == "aws" and config.get("region") == self.region and config.get("apiBaseUrl") == api})
        checks.append({"name": "javascript", "passed": fetch_url(website + "/app.js")[0] == 200})
        checks.append({"name": "unauthenticated_api", "passed": fetch_url(api + "/api/health")[0] == 401})
        status, headers, _ = fetch_url(api + "/api/state", "OPTIONS", {"Origin": website, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"})
        headers = {key.lower(): value for key, value in headers.items()}
        checks.append({"name": "dashboard_cors", "passed": status == 204 and headers.get("access-control-allow-origin") == website and "authorization" in headers.get("access-control-allow-headers", "").lower()})
        checks.append({"name": "private_s3", "passed": fetch_url("https://" + bucket + ".s3." + self.region + ".amazonaws.com/index.html")[0] == 403})
        passed = all(check["passed"] for check in checks)
        self.report("cloud-smoke", {"passed": passed, "checks": checks, "fleetMutated": False})
        if not passed:
            raise RuntimeError("A read-only public cloud check failed")
        self.authenticated_health()

    def authenticated_health(self):
        configured = self.env.get("EDGEOPS_CLOUD_SMOKE_HELPER")
        if not configured:
            return
        helper = Path(configured).resolve()
        if not helper.is_file() or helper.parent != self.aws_helper.parent:
            raise ValueError("Authenticated health requires the reviewed workspace helper")
        report = self.reports / "authenticated-health.json"
        self.run([self.python, helper, "--report", report])
        payload = json.loads(report.read_text(encoding="utf-8"))
        if payload.get("passed") is not True or payload.get("secretsRecorded") is not False:
            raise ValueError("Authenticated health did not produce a successful sanitized report")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("tests", "docker", "validate", "plan", "apply", "smoke"))
    parser.add_argument("--approved", action="store_true")
    args = parser.parse_args()
    try:
        runner = Pipeline()
        stages = {"tests": runner.tests, "docker": runner.docker_check, "validate": runner.terraform_validate,
                  "plan": runner.plan, "apply": lambda: runner.apply_deployment(args.approved), "smoke": runner.cloud_check}
        stages[args.stage]()
        return 0
    except (ValueError, RuntimeError, KeyError, OSError, json.JSONDecodeError) as error:
        print("Pipeline stage failed: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
