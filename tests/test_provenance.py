from __future__ import annotations

import math
import os
import tempfile
import unittest
from pathlib import Path

from benchlog.provenance import flatten_metrics, git_state, read_json, system_environment
from benchlog.storage import BenchLogError


class ProvenanceTests(unittest.TestCase):
    def test_flattens_nested_numeric_metrics(self) -> None:
        result = flatten_metrics({"loss": {"train": 0.5}, "accuracy": 1})
        self.assertEqual(result, {"accuracy": 1.0, "loss.train": 0.5})

    def test_rejects_non_numeric_metric(self) -> None:
        with self.assertRaisesRegex(BenchLogError, "must be numeric"):
            flatten_metrics({"label": "good"})

    def test_rejects_boolean_and_nonfinite_metrics(self) -> None:
        for value in (True, math.inf, math.nan):
            with self.subTest(value=value), self.assertRaises(BenchLogError):
                flatten_metrics({"bad": value})

    def test_reports_json_location(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"x": }')
            with self.assertRaisesRegex(BenchLogError, "line 1, column"):
                read_json(path, label="metrics")

    def test_captures_only_named_environment_variables(self) -> None:
        os.environ["BENCHLOG_TEST_VALUE"] = "visible"
        result = system_environment(["BENCHLOG_TEST_VALUE", "BENCHLOG_MISSING_VALUE"])
        self.assertEqual(
            result["requested_variables"],
            {"BENCHLOG_TEST_VALUE": "visible", "BENCHLOG_MISSING_VALUE": None},
        )
        self.assertNotIn("PATH", result["requested_variables"])

    def test_rejects_invalid_environment_name(self) -> None:
        with self.assertRaisesRegex(BenchLogError, "invalid environment"):
            system_environment(["NOT-VALID"])

    def test_non_repository_has_no_git_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(git_state(Path(directory)))


if __name__ == "__main__":
    unittest.main()
