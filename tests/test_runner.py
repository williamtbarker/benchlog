from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from benchlog.runner import RunRequest, run_command
from benchlog.storage import init_workspace, load_run


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = init_workspace(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_request(self, command: list[str], **changes: object):
        values: dict[str, object] = {
            "store": self.store,
            "name": "unit-test",
            "command": command,
            "cwd": self.root,
            "quiet": True,
        }
        values.update(changes)
        return run_command(RunRequest(**values))  # type: ignore[arg-type]

    def test_success_captures_output_config_metrics_and_artifact(self) -> None:
        (self.root / "config.json").write_text('{"learning_rate": 0.01}')
        script = (
            "import json,pathlib; "
            "print('training'); "
            "print('warning', file=__import__('sys').stderr); "
            "metrics={'loss': {'test': 0.25}, 'accuracy': 0.9}; "
            "pathlib.Path('metrics.json').write_text(json.dumps(metrics)); "
            "pathlib.Path('model.bin').write_bytes(b'model')"
        )
        record = self.run_request(
            [sys.executable, "-c", script],
            config=Path("config.json"),
            metrics=Path("metrics.json"),
            artifacts=[Path("model.bin")],
            tags=["ml", "demo", "ml"],
        )
        self.assertEqual(record.status, "succeeded")
        self.assertEqual(record.exit_code, 0)
        self.assertEqual(record.metrics, {"accuracy": 0.9, "loss.test": 0.25})
        self.assertEqual(record.tags, ["demo", "ml"])
        paths = {item.path for item in record.files}
        self.assertEqual(
            paths,
            {"artifacts/model.bin", "config.json", "metrics.json", "stderr.log", "stdout.log"},
        )
        run_directory = self.store / "runs" / record.run_id
        self.assertEqual((run_directory / "stdout.log").read_text(), "training\n")
        self.assertEqual((run_directory / "stderr.log").read_text(), "warning\n")
        self.assertEqual(load_run(self.store, record.run_id).status, "succeeded")

    def test_failed_child_preserves_exit_code(self) -> None:
        record = self.run_request([sys.executable, "-c", "raise SystemExit(7)"])
        self.assertEqual((record.status, record.exit_code), ("failed", 7))

    def test_missing_executable_is_recorded(self) -> None:
        record = self.run_request(["definitely-no-such-benchlog-command"])
        self.assertEqual((record.status, record.exit_code), ("failed", 127))
        self.assertIsNotNone(record.error)

    def test_timeout_is_recorded(self) -> None:
        record = self.run_request(
            [sys.executable, "-c", "import time; time.sleep(2)"], timeout_seconds=0.05
        )
        self.assertEqual((record.status, record.exit_code), ("timed_out", 124))

    def test_bad_post_run_metrics_leave_a_diagnostic_manifest(self) -> None:
        script = "from pathlib import Path; Path('metrics.json').write_text('{bad')"
        record = self.run_request([sys.executable, "-c", script], metrics=Path("metrics.json"))
        self.assertEqual((record.status, record.exit_code), ("error", 2))
        self.assertIn("invalid JSON", record.error or "")

    def test_requested_environment_is_recorded_without_full_environment(self) -> None:
        os.environ["BENCHLOG_VISIBLE"] = "yes"
        record = self.run_request(
            [sys.executable, "-c", "pass"], environment_names=["BENCHLOG_VISIBLE"]
        )
        requested = record.environment["requested_variables"]
        self.assertEqual(requested, {"BENCHLOG_VISIBLE": "yes"})
        self.assertNotIn("PATH", requested)

    def test_duplicate_artifact_names_are_disambiguated(self) -> None:
        first = self.root / "first"
        second = self.root / "second"
        first.mkdir()
        second.mkdir()
        (first / "result.txt").write_text("one")
        (second / "result.txt").write_text("two")
        record = self.run_request(
            [sys.executable, "-c", "pass"],
            artifacts=[first / "result.txt", second / "result.txt"],
        )
        paths = {item.path for item in record.files if item.role == "artifact"}
        self.assertEqual(paths, {"artifacts/result.txt", "artifacts/result-2.txt"})


if __name__ == "__main__":
    unittest.main()
