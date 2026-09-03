from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from benchlog.models import RunRecord
from benchlog.query import metric_matrix, recover_run, select_runs, verify_run
from benchlog.storage import BenchLogError, init_workspace, load_run, new_run_directory, save_run
from tests.helpers import successful_run


class QueryTests(unittest.TestCase):
    def test_verify_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = successful_run(root)
            store = root / ".benchlog"
            self.assertEqual(verify_run(store, record.run_id), [])
            (store / "runs" / record.run_id / "stdout.log").write_text("changed")
            issues = verify_run(store, record.run_id)
            self.assertEqual(len(issues), 1)
            self.assertIn("mismatch", issues[0].problem)

    def test_filters_by_status_and_tag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = successful_run(root, "first")
            store = root / ".benchlog"
            first.tags = ["baseline"]
            save_run(store, first)
            successful_run(root, "second")
            selected = select_runs(store, status="succeeded", tag="baseline")
            self.assertEqual([item.name for item in selected], ["first"])

    def test_metric_matrix_has_stable_columns(self) -> None:
        base = dict(status="succeeded", command=["true"], cwd="/tmp", started_at="now")
        first = RunRecord("one", "a", metrics={"loss": 0.4}, **base)
        second = RunRecord("two", "b", metrics={"accuracy": 0.8, "loss": 0.2}, **base)
        headers, rows = metric_matrix([first, second])
        self.assertEqual(headers, ["run_id", "name", "status", "accuracy", "loss"])
        self.assertEqual(rows[0][-2:], ["", "0.4"])

    def test_recovers_abandoned_running_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = init_workspace(Path(directory))
            run_id, _ = new_run_directory(store)
            record = RunRecord(
                run_id, "old", "running", ["train"], directory, "2026-01-01T00:00:00Z"
            )
            save_run(store, record)
            recovered = recover_run(store, run_id, "machine rebooted")
            self.assertEqual((recovered.status, recovered.exit_code), ("interrupted", 130))
            self.assertEqual(load_run(store, run_id).error, "machine rebooted")

    def test_recover_rejects_finished_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = successful_run(root)
            with self.assertRaisesRegex(BenchLogError, "not running"):
                recover_run(root / ".benchlog", record.run_id, "no")


if __name__ == "__main__":
    unittest.main()
