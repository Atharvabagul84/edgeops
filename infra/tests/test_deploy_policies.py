"""Offline checks of the GitHub deploy roles rendered from infra/bootstrap/policies.

The trust evaluation covers only the condition operators the templates use
(StringEquals and StringLike). It shows the intent of the policies; AWS stays
the authority, and the deploy workflow repeats the PR check against real STS.
"""
import fnmatch
import json
from pathlib import Path
from string import Template
import unittest

POLICIES = Path(__file__).resolve().parents[1] / "bootstrap" / "policies"
REPO = "Atharvabagul84/edgeops"
VARS = dict(partition="aws", region="ap-southeast-2", account_id="123456789012", project="edgeops-demo",
            state_bucket="edgeops-tfstate-123456789012-ap-southeast-2",
            state_key="edgeops-demo/terraform.tfstate", deploy_role_prefix="edgeops-github-",
            boundary_arn="arn:aws:iam::123456789012:policy/edgeops-demo-workload-boundary",
            provider_arn="arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com")
SUBJECTS = {"plan": [f"repo:{REPO}:pull_request"], "apply": [f"repo:{REPO}:environment:production"]}


def render(name, **extra):
    return json.loads(Template((POLICIES / name).read_text(encoding="utf-8")).substitute(VARS, **extra))


def trust(role):
    return render("github-trust.json.tpl", subjects=json.dumps(SUBJECTS[role]))


def matches(operator, expected, actual):
    values = expected if isinstance(expected, list) else [expected]
    if actual is None:
        return False
    if operator == "StringEquals":
        return actual in values
    if operator == "StringLike":
        return any(fnmatch.fnmatchcase(actual, value) for value in values)
    raise NotImplementedError(operator)


def can_assume(policy, claims):
    for statement in policy["Statement"]:
        if statement["Effect"] == "Allow" and statement["Action"] == "sts:AssumeRoleWithWebIdentity" and all(
                matches(operator, expected, claims.get(key))
                for operator, condition in statement.get("Condition", {}).items()
                for key, expected in condition.items()):
            return True
    return False


def token(sub, aud="sts.amazonaws.com"):
    return {"token.actions.githubusercontent.com:sub": sub, "token.actions.githubusercontent.com:aud": aud}


def actions(statement):
    value = statement["Action"]
    return value if isinstance(value, list) else [value]


def resources(statement):
    value = statement["Resource"]
    return value if isinstance(value, list) else [value]


class TrustTests(unittest.TestCase):
    def test_pull_request_token_cannot_assume_the_apply_role(self):
        self.assertFalse(can_assume(trust("apply"), token(f"repo:{REPO}:pull_request")))
        self.assertTrue(can_assume(trust("plan"), token(f"repo:{REPO}:pull_request")))

    def test_only_the_production_environment_can_assume_the_apply_role(self):
        self.assertTrue(can_assume(trust("apply"), token(f"repo:{REPO}:environment:production")))
        for sub in [f"repo:{REPO}:ref:refs/heads/main", f"repo:{REPO}:environment:staging",
                    f"repo:{REPO}:environment:production-copy", "repo:someone/edgeops:environment:production",
                    f"repo:{REPO}-fork:environment:production", f"repo:{REPO}:*"]:
            with self.subTest(sub=sub):
                self.assertFalse(can_assume(trust("apply"), token(sub)))

    def test_wrong_audience_is_rejected(self):
        self.assertFalse(can_assume(trust("apply"), token(f"repo:{REPO}:environment:production", aud="other")))

    def test_trust_uses_exact_match_and_no_hard_coded_repository_id(self):
        text = (POLICIES / "github-trust.json.tpl").read_text(encoding="utf-8")
        self.assertNotIn("StringLike", text)
        self.assertNotIn("repository_id", text)
        self.assertNotRegex(text, r"\d{6,}")


class PermissionTests(unittest.TestCase):
    def setUp(self):
        self.apply = render("deploy-apply.json.tpl")
        self.read = render("deploy-read.json.tpl")
        self.boundary = render("workload-boundary.json.tpl")

    def statement(self, policy, sid):
        return next(item for item in policy["Statement"] if item["Sid"] == sid)

    def test_roles_can_only_be_created_or_given_policies_with_the_boundary(self):
        statement = self.statement(self.apply, "ChangeWorkloadRolesOnlyWithBoundary")
        self.assertEqual(statement["Condition"], {"StringEquals": {"iam:PermissionsBoundary": VARS["boundary_arn"]}})
        guarded = {"iam:CreateRole", "iam:PutRolePolicy", "iam:AttachRolePolicy", "iam:PutRolePermissionsBoundary"}
        for item in self.apply["Statement"]:
            if item["Effect"] == "Allow" and item["Sid"] != statement["Sid"]:
                self.assertFalse(guarded & set(actions(item)), item["Sid"])

    def test_pass_role_is_scoped_by_arn_and_service(self):
        statement = self.statement(self.apply, "PassOnlyLambdaRolesToLambda")
        self.assertEqual(resources(statement), ["arn:aws:iam::123456789012:role/edgeops-demo-api",
                                                "arn:aws:iam::123456789012:role/edgeops-demo-worker"])
        self.assertEqual(statement["Condition"]["StringEquals"]["iam:PassedToService"], "lambda.amazonaws.com")
        for item in self.apply["Statement"] + self.read["Statement"]:
            if item["Sid"] != statement["Sid"]:
                self.assertNotIn("iam:PassRole", actions(item))

    def test_boundary_and_deploy_roles_cannot_be_weakened(self):
        denied = set(actions(self.statement(self.apply, "NeverWeakenTheBoundaryOrCreateCredentials")))
        self.assertTrue({"iam:DeleteRolePermissionsBoundary", "iam:CreatePolicyVersion",
                         "iam:SetDefaultPolicyVersion", "iam:CreateAccessKey"} <= denied)
        deploy = self.statement(self.apply, "NeverTouchDeployRoles")
        self.assertEqual((deploy["Effect"], deploy["Action"]), ("Deny", "iam:*"))
        self.assertTrue(resources(deploy)[0].endswith(":role/edgeops-github-*"))

    def test_no_wildcard_actions_and_unscoped_writes_are_conditioned(self):
        read_only = ("Get", "List", "Describe")
        unscoped_writes = {"EventSourceMappingsForOwnFunctions", "OperatorUserPoolCreate", "HttpApiAccessLogDelivery"}
        for policy in (self.apply, self.read, self.boundary):
            for item in policy["Statement"]:
                if item["Effect"] != "Allow":
                    continue
                for action in actions(item):
                    self.assertNotEqual(action, "*")
                    self.assertFalse(action.endswith(":*"), action)
                if "*" in resources(item) and item["Sid"] not in unscoped_writes:
                    for action in actions(item):
                        verb = action.split(":", 1)[1]
                        self.assertTrue(verb.startswith(read_only) or action == "apigateway:GET", action)

    def test_boundary_grants_only_the_lambda_runtime_needs(self):
        granted = {action for item in self.boundary["Statement"] for action in actions(item)}
        self.assertEqual(granted, {"logs:CreateLogStream", "logs:PutLogEvents", "dynamodb:GetItem",
                                   "dynamodb:BatchGetItem", "dynamodb:PutItem", "sqs:SendMessage",
                                   "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"})
        for item in self.boundary["Statement"]:
            self.assertTrue(all(":123456789012:" in arn and "edgeops-demo-" in arn for arn in resources(item)))

    def test_plan_role_can_only_write_the_state_lock(self):
        writes = [(action, arn) for item in self.read["Statement"] for action in actions(item)
                  for arn in resources(item) if action.startswith("s3:Put") or action.startswith("s3:Delete")]
        lock = f"arn:aws:s3:::{VARS['state_bucket']}/{VARS['state_key']}.tflock"
        self.assertEqual(writes, [("s3:PutObject", lock), ("s3:DeleteObject", lock)])

    def test_state_bucket_is_outside_the_frontend_bucket_wildcard(self):
        self.assertFalse(fnmatch.fnmatchcase(VARS["state_bucket"], VARS["project"] + "-*"))
        denied = set(actions(self.statement(self.apply, "NeverWeakenStateBucket")))
        self.assertTrue({"s3:DeleteBucket", "s3:PutBucketPolicy", "s3:PutBucketVersioning"} <= denied)


if __name__ == "__main__":
    unittest.main()
