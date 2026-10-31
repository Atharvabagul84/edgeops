"""Deploy-workflow plan summary tests. No Terraform or AWS calls are made."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from scripts import plan_summary


def change(address, *actions):
    return {"address": address, "mode": "managed", "change": {"actions": list(actions)}}


class PlanSummaryTests(unittest.TestCase):
    def run_summary(self, plan, *flags):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "plan.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = plan_summary.main([str(path), *flags])
        return code, output.getvalue()

    def test_counts_actions_and_treats_forget_as_safe(self):
        plan = {"resource_changes": [change("aws_dynamodb_table.fleet", "create"),
                                     change("aws_iam_role.lambda", "update"),
                                     change("aws_dynamodb_table.state", "forget"),
                                     {"address": "data.x", "mode": "data", "change": {"actions": ["read"]}}]}
        code, output = self.run_summary(plan)
        self.assertEqual(code, 0)
        self.assertIn("| create | 1 |", output)
        self.assertIn("| forget | 1 |", output)
        self.assertNotIn("read", output)

    def test_delete_or_replace_is_refused_unless_allowed(self):
        plan = {"resource_changes": [change("aws_sqs_queue.telemetry", "delete", "create"),
                                     change("aws_sns_topic.alerts", "delete")]}
        code, output = self.run_summary(plan)
        self.assertEqual(code, 1)
        self.assertIn("| replace | 1 |", output)
        self.assertIn("`aws_sns_topic.alerts`", output)
        self.assertEqual(self.run_summary(plan, "--allow-delete")[0], 0)

    def test_reports_whether_the_legacy_code_only_policy_would_accept(self):
        plan = {"variables": {"region": {"value": "ap-southeast-2"}},
                "resource_changes": [change("aws_dynamodb_table.fleet", "create")]}
        _, output = self.run_summary(plan, "--account", "123456789012", "--region", "ap-southeast-2")
        self.assertIn("code-only release policy: no", output)


if __name__ == "__main__":
    unittest.main()
