"""Fail-closed policy for updates to the existing EdgeOps demo deployment."""
import base64
import hashlib
import re
import time
from pathlib import Path


def check_identity(identity, expected_account):
    if not re.fullmatch(r"\d{12}", expected_account) or identity.get("Account") != expected_account:
        raise ValueError("AWS identity does not match the configured deployment account")


def _resources(module):
    yield from module.get("resources", [])
    for child in module.get("child_modules", []):
        yield from _resources(child)


def _has_unknown(value):
    if isinstance(value, dict):
        return any(_has_unknown(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_unknown(item) for item in value)
    return value is True


def review_plan(plan, expected_account, expected_region, project):
    if plan.get("errored") or plan.get("complete") is False or plan.get("deferred_changes"):
        raise ValueError("Only a complete, successful Terraform plan can be reviewed")
    if plan.get("variables", {}).get("region", {}).get("value") != expected_region:
        raise ValueError("Terraform Region differs from the approved project Region")
    identities = [item.get("values", {}).get("account_id") for item in _resources(
        plan.get("planned_values", {}).get("root_module", {}))
        if item.get("address") == "data.aws_caller_identity.current"]
    if not identities:
        # Terraform omits unchanged data sources from planned_values. The
        # refreshed prior_state is usable only when no new identity read/change
        # is pending; a deferred read must never inherit a stale account value.
        pending_identity = any(item.get("address") == "data.aws_caller_identity.current"
                               for item in plan.get("resource_changes", []))
        if not pending_identity:
            identities = [item.get("values", {}).get("account_id") for item in _resources(
                plan.get("prior_state", {}).get("values", {}).get("root_module", {}))
                if item.get("address") == "data.aws_caller_identity.current"]
    if identities != [expected_account]:
        raise ValueError("Terraform plan does not identify the approved AWS account")
    planned_changes = {item.get("address"): item for item in plan.get("resource_changes", [])}
    refresh_only_drift = []
    for drift in plan.get("resource_drift", []):
        if drift.get("mode") == "managed" and drift.get("change", {}).get("actions") != ["no-op"]:
            proposed = planned_changes.get(drift.get("address"), {})
            if proposed.get("mode") != "managed" or proposed.get("change", {}).get("actions") != ["no-op"]:
                raise ValueError("Drift without a matching non-mutating plan requires separate review")
            # Refresh metadata is not an AWS mutation. This policy restricts
            # proposed changes; it does not claim to audit all remote drift.
            refresh_only_drift.append(drift["address"])
    updates = []
    for entry in plan.get("resource_changes", []):
        change = entry.get("change", {})
        actions = change.get("actions")
        address = entry.get("address", "")
        if entry.get("previous_address") or entry.get("deposed") or change.get("importing") or change.get("replace_paths"):
            raise ValueError("Moves, imports, deposed resources and replacements are outside this pipeline")
        if entry.get("mode") == "data" and actions in (["read"], ["no-op"]):
            continue
        if entry.get("mode") != "managed" or actions not in (["no-op"], ["update"]):
            raise ValueError("Creation, deletion, replacement or unrecognized actions are forbidden")
        if actions == ["no-op"]:
            continue
        if entry.get("provider_name", "registry.terraform.io/hashicorp/aws") != "registry.terraform.io/hashicorp/aws":
            raise ValueError("Unexpected provider for a deployment change")
        before, after = change.get("before"), change.get("after")
        if not isinstance(before, dict) or not isinstance(after, dict) or not before.get("id"):
            raise ValueError("Only existing resources can be updated")
        changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
        changed |= {key for key, value in change.get("after_unknown", {}).items() if _has_unknown(value)}
        if address in ('aws_lambda_function.service["api"]', 'aws_lambda_function.service["worker"]') and entry.get("type") == "aws_lambda_function":
            allowed = {"source_code_hash", "code_sha256", "source_code_size", "last_modified", "qualified_arn", "qualified_invoke_arn", "version"}
            package = (Path(project) / "infra/.lambda.zip").resolve()
            filename = after.get("filename")
            if not isinstance(filename, str) or (Path(project) / "infra" / filename).resolve() != package or not package.is_file():
                raise ValueError("Lambda code must use the fingerprinted deployment ZIP")
            package_hash = base64.b64encode(bytes.fromhex(_digest(package))).decode("ascii")
            if after.get("source_code_hash") != package_hash:
                raise ValueError("Lambda ZIP bytes differ from the code hash in the saved plan")
        elif re.fullmatch(r'aws_s3_object\.frontend\["[^"\r\n]+"\]', address) and entry.get("type") == "aws_s3_object":
            allowed = {"etag", "source_hash", "version_id", "checksum_crc32", "checksum_crc32c", "checksum_crc64nvme", "checksum_sha1", "checksum_sha256"}
            source = after.get("source")
            if not isinstance(source, str):
                raise ValueError("Frontend objects must use a known local source file")
            source_path = (Path(project) / "infra" / source).resolve()
            frontend = (Path(project) / "frontend").resolve()
            if not source_path.is_relative_to(frontend) or not source_path.is_file():
                raise ValueError("Frontend source must remain inside the frontend directory")
            if after.get("etag") != hashlib.md5(source_path.read_bytes(), usedforsecurity=False).hexdigest():
                raise ValueError("Frontend source bytes differ from the etag in the saved plan")
        else:
            raise ValueError("Only Lambda code and existing frontend object bytes may change")
        if not changed <= allowed:
            raise ValueError("Resource configuration or permissions changed outside the code-only allowance")
        updates.append({"address": address, "fields": sorted(changed)})
    return {"account": expected_account, "region": expected_region, "updates": updates,
            "changeCount": len(updates), "refreshOnlyDrift": refresh_only_drift}


def _digest(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def fingerprint(project):
    root = Path(project).resolve()
    files = set()
    for folder, pattern in (("frontend", "**/*"), ("backend", "**/*.py"), ("infra", "*.tf"), ("infra", "*.tfvars"), ("scripts", "pipeline*.py")):
        files.update(path for path in (root / folder).glob(pattern) if path.is_file())
    for name in ("infra/.lambda.zip", "infra/.terraform.lock.hcl", "Jenkinsfile"):
        if (root / name).is_file():
            files.add(root / name)
    result = {}
    for path in sorted(files):
        if not path.resolve().is_relative_to(root):
            raise ValueError("Deployment inputs must not link outside the project")
        result[path.relative_to(root).as_posix()] = _digest(path)
    return result


def make_manifest(project, plan_path, account, region, now=None):
    return {"createdAt": time.time() if now is None else now, "account": account, "region": region,
            "planSha256": _digest(plan_path), "inputs": fingerprint(project)}


def verify_manifest(project, plan_path, manifest, account, region, now=None):
    now = time.time() if now is None else now
    if manifest.get("account") != account or manifest.get("region") != region:
        raise ValueError("Saved plan belongs to a different deployment target")
    age = now - manifest.get("createdAt", 0)
    if age < 0 or age > 3600:
        raise ValueError("Saved plan is older than one hour; run a new build")
    if manifest.get("planSha256") != _digest(plan_path):
        raise ValueError("Saved plan changed after review")
    if manifest.get("inputs") != fingerprint(project):
        raise ValueError("Deployment source or ZIP changed after plan review")


def loopback_url(binding):
    match = re.fullmatch(r"127\.0\.0\.1:(\d+)\s*", binding)
    if not match or not 1 <= int(match.group(1)) <= 65535:
        raise ValueError("The smoke-test container must publish only to IPv4 loopback")
    return "http://127.0.0.1:" + match.group(1)
