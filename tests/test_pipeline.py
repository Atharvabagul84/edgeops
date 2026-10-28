"""Deployment-policy tests. No AWS or Docker calls are made."""
import json
import base64
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from scripts import pipeline_policy as policy
except ImportError:
    policy = None

try:
    from scripts import pipeline
except ImportError:
    pipeline = None

ACCOUNT = "123456789012"
REGION = "ap-southeast-2"


def plan_fixture():
    return {
        "variables": {"region": {"value": REGION}},
        "planned_values": {"root_module": {"resources": [
            {"address": "data.aws_caller_identity.current", "values": {"account_id": ACCOUNT}}
        ]}},
        "resource_changes": [],
    }


def update(address, kind, before, after, unknown=None):
    return {"address": address, "type": kind, "mode": "managed", "change": {
        "actions": ["update"], "before": before, "after": after,
        "after_unknown": unknown or {},
    }}


class PipelinePolicyTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(policy, "The deployment guard must exist before the pipeline can deploy")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        (self.project / "frontend").mkdir()
        (self.project / "infra").mkdir()
        (self.project / "frontend/app.js").write_text("original", encoding="utf-8")
        (self.project / "infra/.lambda.zip").write_bytes(b"zip-code")

    def review(self, value):
        return policy.review_plan(value, ACCOUNT, REGION, self.project)

    def test_no_change_plan_passes(self):
        self.assertEqual(self.review(plan_fixture())["updates"], [])

    def test_wrong_identity_is_rejected(self):
        with self.assertRaises(ValueError):
            policy.check_identity({"Account": "111111111111"}, ACCOUNT)

    def test_wrong_plan_region_is_rejected(self):
        value = plan_fixture()
        value["variables"]["region"]["value"] = "ap-south-1"
        with self.assertRaises(ValueError):
            self.review(value)

    def test_wrong_plan_account_is_rejected(self):
        value = plan_fixture()
        value["planned_values"]["root_module"]["resources"][0]["values"]["account_id"] = "111111111111"
        with self.assertRaises(ValueError):
            self.review(value)

    def test_unchanged_identity_omitted_from_planned_values_uses_resolved_prior_state(self):
        # Actual Terraform 1.9.8 no-op plan: unchanged data sources are omitted
        # from planned_values but their refreshed values remain in prior_state.
        value = plan_fixture()
        value["prior_state"] = {"values": value["planned_values"]}
        value["planned_values"] = {"root_module": {"resources": []}}
        try:
            reviewed = self.review(value)
        except ValueError as error:
            self.fail("Resolved prior-state caller identity was rejected: " + str(error))
        self.assertEqual(reviewed["account"], ACCOUNT)

    def test_prior_state_identity_still_must_match_the_expected_account(self):
        value = plan_fixture()
        value["planned_values"]["root_module"]["resources"][0]["values"]["account_id"] = "111111111111"
        value["prior_state"] = {"values": value["planned_values"]}
        value["planned_values"] = {"root_module": {"resources": []}}
        with self.assertRaises(ValueError):
            self.review(value)

    def test_pending_identity_read_cannot_fall_back_to_old_identity(self):
        value = plan_fixture()
        value["prior_state"] = {"values": value["planned_values"]}
        value["planned_values"] = {"root_module": {"resources": []}}
        value["resource_changes"] = [{"address": "data.aws_caller_identity.current", "mode": "data",
            "type": "aws_caller_identity", "change": {"actions": ["read"], "after_unknown": {"account_id": True}}}]
        with self.assertRaises(ValueError):
            self.review(value)

    def test_refresh_drift_is_informational_when_proposed_resource_is_noop(self):
        value = plan_fixture()
        address = "aws_cognito_user_pool.operators"
        value["resource_drift"] = [update(address, "aws_cognito_user_pool",
            {"id": "pool", "estimated_number_of_users": 0}, {"id": "pool", "estimated_number_of_users": 1})]
        value["resource_changes"] = [{"address": address, "mode": "managed", "type": "aws_cognito_user_pool",
            "change": {"actions": ["no-op"]}}]
        try:
            reviewed = self.review(value)
        except ValueError as error:
            self.fail("Non-mutating refresh metadata was rejected: " + str(error))
        self.assertEqual(reviewed["updates"], [])
        self.assertEqual(reviewed["refreshOnlyDrift"], [address])

    def test_refresh_drift_cannot_hide_a_proposed_iam_update(self):
        value = plan_fixture()
        entry = update("aws_iam_role_policy.lambda", "aws_iam_role_policy", {"id": "policy", "policy": "old"}, {"id": "policy", "policy": "new"})
        value["resource_drift"] = [entry]
        value["resource_changes"] = [entry]
        with self.assertRaises(ValueError):
            self.review(value)

    def test_unmatched_drift_remains_blocked(self):
        value = plan_fixture()
        value["resource_drift"] = [update("aws_iam_role_policy.lambda", "aws_iam_role_policy", {"id": "policy"}, {"id": "policy", "policy": "new"})]
        with self.assertRaises(ValueError):
            self.review(value)

    def test_create_delete_and_replacement_are_rejected(self):
        for actions in (["create"], ["delete"], ["delete", "create"], ["forget"]):
            with self.subTest(actions=actions):
                value = plan_fixture()
                entry = update('aws_lambda_function.service["api"]', "aws_lambda_function", {}, {})
                entry["change"]["actions"] = actions
                value["resource_changes"] = [entry]
                with self.assertRaises(ValueError):
                    self.review(value)

    def test_lambda_code_update_passes(self):
        value = plan_fixture()
        value["resource_changes"] = [update('aws_lambda_function.service["api"]', "aws_lambda_function",
            {"id": "edgeops-demo-api", "source_code_hash": "old", "role": "same", "filename": "./.lambda.zip"},
            {"id": "edgeops-demo-api", "source_code_hash": base64.b64encode(hashlib.sha256(b"zip-code").digest()).decode(), "role": "same", "filename": "./.lambda.zip"},
            {"last_modified": True})]
        self.assertEqual(len(self.review(value)["updates"]), 1)

    def test_lambda_role_environment_and_unknown_changes_are_rejected(self):
        for field in ("role", "environment", "vpc_config", "runtime", "memory_size"):
            with self.subTest(field=field):
                value = plan_fixture()
                value["resource_changes"] = [update('aws_lambda_function.service["api"]', "aws_lambda_function",
                    {"id": "api", field: "old"}, {"id": "api", field: "new"})]
                with self.assertRaises(ValueError):
                    self.review(value)
        value["resource_changes"] = [update('aws_lambda_function.service["api"]', "aws_lambda_function",
            {"id": "api"}, {"id": "api"}, {"environment": True})]
        with self.assertRaises(ValueError):
            self.review(value)

    def test_iam_and_other_infrastructure_updates_are_rejected(self):
        for kind in ("aws_iam_role_policy", "aws_s3_bucket_policy", "aws_cognito_user_pool", "aws_dynamodb_table"):
            value = plan_fixture()
            value["resource_changes"] = [update(kind + ".example", kind, {"id": "same"}, {"id": "same", "x": 1})]
            with self.assertRaises(ValueError):
                self.review(value)

    def test_existing_frontend_content_update_passes(self):
        value = plan_fixture()
        before = {"id": "app.js", "bucket": "same", "key": "app.js", "source": "../frontend/app.js", "etag": "old"}
        after = dict(before, etag=hashlib.md5(b"original").hexdigest())
        value["resource_changes"] = [update('aws_s3_object.frontend["app.js"]', "aws_s3_object", before, after)]
        self.assertEqual(len(self.review(value)["updates"]), 1)

    def test_s3_acl_and_outside_source_are_rejected(self):
        value = plan_fixture()
        before = {"id": "app.js", "bucket": "same", "key": "app.js", "source": "../frontend/app.js", "etag": "old"}
        for after in (dict(before, acl="public-read"), dict(before, source="../../private.txt")):
            value["resource_changes"] = [update('aws_s3_object.frontend["app.js"]', "aws_s3_object", before, after)]
            with self.assertRaises(ValueError):
                self.review(value)

    def test_false_unknown_scaffolding_is_not_a_configuration_change(self):
        value = plan_fixture()
        before = {"id": "app.js", "key": "app.js", "source": "../frontend/app.js", "etag": "old"}
        value["resource_changes"] = [update('aws_s3_object.frontend["app.js"]', "aws_s3_object", before,
            dict(before, etag=hashlib.md5(b"original").hexdigest()), {"metadata": {}, "tags_all": {}, "scaffold": [{"nested": False}]})]
        self.assertEqual(len(self.review(value)["updates"]), 1)

    def test_source_bytes_must_match_the_hash_inside_the_plan(self):
        value = plan_fixture()
        before = {"id": "app.js", "key": "app.js", "source": "../frontend/app.js", "etag": "old"}
        value["resource_changes"] = [update('aws_s3_object.frontend["app.js"]', "aws_s3_object", before,
            dict(before, etag="a" * 32))]
        with self.assertRaises(ValueError):
            self.review(value)

    def test_import_move_and_deferred_work_are_rejected(self):
        for field, content in (("importing", {"id": "external"}), ("previous_address", "old.address")):
            value = plan_fixture()
            entry = update('aws_lambda_function.service["api"]', "aws_lambda_function", {"id": "api"}, {"id": "api"})
            if field == "importing":
                entry["change"][field] = content
            else:
                entry[field] = content
            value["resource_changes"] = [entry]
            with self.assertRaises(ValueError):
                self.review(value)
        value = plan_fixture()
        value["deferred_changes"] = [{}]
        with self.assertRaises(ValueError):
            self.review(value)

    def test_mutation_of_saved_plan_is_detected(self):
        path = self.project / "infra/deploy.tfplan"
        path.write_bytes(b"approved")
        manifest = policy.make_manifest(self.project, path, ACCOUNT, REGION, now=1000)
        path.write_bytes(b"different")
        with self.assertRaises(ValueError):
            policy.verify_manifest(self.project, path, manifest, ACCOUNT, REGION, now=1010)

    def test_source_change_or_new_asset_after_plan_is_detected(self):
        path = self.project / "infra/deploy.tfplan"
        path.write_bytes(b"approved")
        manifest = policy.make_manifest(self.project, path, ACCOUNT, REGION, now=1000)
        (self.project / "frontend/new.js").write_text("new", encoding="utf-8")
        with self.assertRaises(ValueError):
            policy.verify_manifest(self.project, path, manifest, ACCOUNT, REGION, now=1010)

    def test_manifest_expiry_and_identity_are_checked(self):
        path = self.project / "infra/deploy.tfplan"
        path.write_bytes(b"approved")
        manifest = policy.make_manifest(self.project, path, ACCOUNT, REGION, now=1000)
        policy.verify_manifest(self.project, path, manifest, ACCOUNT, REGION, now=1010)
        for now, account in ((5000, ACCOUNT), (1010, "111111111111")):
            with self.assertRaises(ValueError):
                policy.verify_manifest(self.project, path, manifest, account, REGION, now=now)

    def test_docker_binding_must_be_loopback(self):
        self.assertEqual(policy.loopback_url("127.0.0.1:49123\n"), "http://127.0.0.1:49123")
        for binding in ("0.0.0.0:49123", "[::]:49123", "127.0.0.1:0", "127.0.0.1:99999"):
            with self.assertRaises(ValueError):
                policy.loopback_url(binding)


class PipelineRunnerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(pipeline, "The pipeline runner must exist")

    def test_apply_requires_explicit_approval_before_any_external_call(self):
        runner = pipeline.Pipeline.__new__(pipeline.Pipeline)
        with self.assertRaises(ValueError):
            runner.apply_deployment(False)

    def test_ambient_credentials_and_terraform_injection_are_blocked(self):
        env = pipeline.clean_environment({"PATH": "keep", "AWS_ACCESS_KEY_ID": "private", "AWS_SECRET_ACCESS_KEY": "secret"})
        self.assertEqual(env.get("PATH"), "keep")
        self.assertNotIn("AWS_ACCESS_KEY_ID", env)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", env)
        with self.assertRaises(ValueError):
            pipeline.clean_environment({"TF_CLI_ARGS_apply": "-destroy"})

    def test_failed_docker_health_check_removes_only_its_named_container(self):
        runner = pipeline.Pipeline.__new__(pipeline.Pipeline)
        runner.env = {}
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, "127.0.0.1:49123\n" if "port" in args else "container-id", "")
        runner.run = run
        runner.report = lambda *args, **kwargs: None
        def failed_fetch(*args, **kwargs):
            raise ValueError("unhealthy")
        with self.assertRaises(ValueError):
            runner.docker_check(fetch=failed_fetch)
        removal = [args for args in calls if args[1:3] == ["rm", "-f"]]
        self.assertEqual(len(removal), 1)
        self.assertEqual(len(removal[0]), 4)
        self.assertTrue(removal[0][3].startswith("edgeops-ci-"))

    def test_authenticated_health_uses_only_reviewed_helper_and_report_path(self):
        self.assertTrue(hasattr(pipeline.Pipeline, "authenticated_health"), "Authenticated health stage is missing")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = root / "cloud_readiness.py"
            helper.write_text("# reviewed helper", encoding="utf-8")
            runner = pipeline.Pipeline.__new__(pipeline.Pipeline)
            runner.env = {"EDGEOPS_CLOUD_SMOKE_HELPER": str(helper)}
            runner.aws_helper = root / "aws_tool.py"
            runner.python = "python"
            runner.reports = root
            calls = []
            def run(args, **kwargs):
                calls.append(args)
                (root / "authenticated-health.json").write_text('{"passed":true,"secretsRecorded":false}', encoding="utf-8")
            runner.run = run
            runner.authenticated_health()
            self.assertEqual(calls, [["python", helper, "--report", root / "authenticated-health.json"]])

    def test_approved_noop_applies_the_same_saved_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = pipeline.Pipeline.__new__(pipeline.Pipeline)
            runner.project = root
            runner.account, runner.region = ACCOUNT, REGION
            runner.plan_file = root / "deployment.tfplan"
            runner.plan_file.write_bytes(b"reviewed plan")
            runner.manifest_file = root / "review.json"
            runner.manifest_file.write_text(json.dumps(policy.make_manifest(root, runner.plan_file, ACCOUNT, REGION)), encoding="utf-8")
            runner.identity = lambda: None
            runner.inspect_plan = lambda: {"updates": []}
            runner.report = lambda *args: None
            calls = []
            runner.tf = lambda *args: calls.append(args)
            runner.apply_deployment(True)
            self.assertEqual(calls, [("apply", "-input=false", "-no-color", "-lock-timeout=30s", str(runner.plan_file))])


if __name__ == "__main__":
    unittest.main()
