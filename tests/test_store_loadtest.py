"""Load-test harness smoke tests against the in-memory table. No AWS calls."""
import contextlib
import io
import unittest

from scripts import store_loadtest
from scripts.memory_dynamo import MemoryDynamo


class LoadTestHarnessTests(unittest.TestCase):
    def test_per_device_store_has_no_conflicts_when_writers_own_devices(self):
        result = store_loadtest.run("fleet", MemoryDynamo(0.001), "t", device_count=6, workers=3, ops=6, batch=2)
        self.assertEqual((result["succeeded"], result["failed"], result["conflicts"]), (18, 0, 0))
        self.assertEqual(result["conditionalWrites"], 18 * 3)  # two readings + one device commit per batch
        self.assertIsNotNone(result["p99Ms"])

    def test_single_item_baseline_runs_and_counts_its_writes(self):
        result = store_loadtest.run("legacy", MemoryDynamo(), "t", device_count=3, workers=1, ops=4, batch=1)
        self.assertEqual((result["succeeded"], result["conflicts"], result["conditionalWrites"]), (4, 0, 4))

    def test_live_runs_need_explicit_confirmation_and_a_test_table(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(SystemExit, "confirm-live"):
                store_loadtest.main(["--backend", "dynamodb", "--table", "edgeops-loadtest"])
            with self.assertRaisesRegex(SystemExit, "dedicated test table"):
                store_loadtest.main(["--backend", "dynamodb", "--table", "edgeops-demo-fleet", "--confirm-live"])


if __name__ == "__main__":
    unittest.main()
