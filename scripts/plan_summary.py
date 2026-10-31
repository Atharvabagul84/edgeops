"""Summarize a `terraform show -json` plan for the GitHub deploy workflow.

Prints a Markdown table of planned actions and whether the plan passes the
legacy Jenkins code-only policy. Exits non-zero when the plan deletes or
replaces resources, unless --allow-delete is given (a reviewed, deliberate run).
"""
import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import pipeline_policy  # noqa: E402


def summarize(plan):
    counts, deleted = collections.Counter(), []
    for entry in plan.get("resource_changes", []):
        if entry.get("mode") != "managed":
            continue
        actions = entry.get("change", {}).get("actions", [])
        label = "replace" if sorted(actions) == ["create", "delete"] else "+".join(actions)
        counts[label] += 1
        if "delete" in actions:
            deleted.append(entry["address"])
    return counts, deleted


def code_only(plan, account, region):
    try:
        pipeline_policy.review_plan(plan, account, region, str(ROOT))
        return "yes"
    except ValueError as error:
        return f"no ({error})"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan_json", type=Path)
    parser.add_argument("--account", default="")
    parser.add_argument("--region", default="")
    parser.add_argument("--allow-delete", action="store_true")
    args = parser.parse_args(argv)
    plan = json.loads(args.plan_json.read_text(encoding="utf-8"))
    counts, deleted = summarize(plan)
    print("| Action | Resources |\n|---|---|")
    for label in ("create", "update", "replace", "delete", "forget", "no-op", "read"):
        if counts.get(label):
            print(f"| {label} | {counts[label]} |")
    if args.account and args.region:
        print(f"\nPasses the legacy code-only release policy: {code_only(plan, args.account, args.region)}")
    if deleted:
        print("\nDeletes or replaces:\n" + "\n".join(f"- `{address}`" for address in deleted))
        if not args.allow_delete:
            print("\nRefusing: re-run the workflow with allow_delete after reviewing these.")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
