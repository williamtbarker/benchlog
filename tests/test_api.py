from __future__ import annotations

import sys
import tempfile
import unittest

from benchlog import BenchLog


class ApiTests(unittest.TestCase):
    def test_library_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = BenchLog.initialize(directory)
            record = log.run(
                "api-demo",
                [sys.executable, "-c", "print('hello')"],
                cwd=directory,
                tags=["api"],
                quiet=True,
            )
            self.assertEqual(log.get(record.run_id[:20]).status, "succeeded")
            self.assertEqual([item.run_id for item in log.runs(tag="api")], [record.run_id])
            self.assertTrue(log.verify(record.run_id))


if __name__ == "__main__":
    unittest.main()
