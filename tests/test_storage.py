from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from benchlog.models import RunRecord
from benchlog.storage import (
    BenchLogError,
    atomic_write_json,
    find_workspace,
    init_workspace,
    iter_runs,
    load_run,
    new_run_directory,
    save_run,
)


class StorageTests(unittest.TestCase):
    def test_initializes_and_discovers_from_child_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = init_workspace(root)
            child = root / "a" / "b"
            child.mkdir(parents=True)
            self.assertEqual(find_workspace(child), store)

    def test_rejects_uninitialized_directory(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(BenchLogError, "benchlog init"),
        ):
            find_workspace(Path(directory))

    def test_atomic_json_is_owner_only_on_posix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "record.json"
            atomic_write_json(target, {"answer": 42})
            self.assertEqual(json.loads(target.read_text()), {"answer": 42})
            if os.name == "posix":
                self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_run_prefix_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = init_workspace(Path(directory))
            run_id, _ = new_run_directory(store)
            record = RunRecord(
                run_id, "demo", "running", ["true"], directory, "2026-01-01T00:00:00Z"
            )
            save_run(store, record)
            self.assertEqual(load_run(store, run_id[:20]).run_id, run_id)

    def test_ambiguous_prefix_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = init_workspace(Path(directory))
            for run_id in ("shared-a", "shared-b"):
                run_directory = store / "runs" / run_id
                run_directory.mkdir()
                save_run(
                    store,
                    RunRecord(
                        run_id, "demo", "running", ["true"], directory, "2026-01-01T00:00:00Z"
                    ),
                )
            with self.assertRaisesRegex(BenchLogError, "ambiguous"):
                load_run(store, "shared")

    def test_iteration_skips_corrupt_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = init_workspace(Path(directory))
            bad = store / "runs" / "bad"
            bad.mkdir()
            (bad / "manifest.json").write_text("not-json")
            self.assertEqual(list(iter_runs(store)), [])


if __name__ == "__main__":
    unittest.main()
