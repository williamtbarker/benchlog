from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from benchlog.cli import main


class CliTests(unittest.TestCase):
    def invoke(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_full_cli_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code, output, _ = self.invoke(["init", str(root)])
            self.assertEqual(code, 0)
            self.assertIn("Initialized", output)

            script = "import json; open('m.json','w').write(json.dumps({'score': .75}))"
            code, _, stderr = self.invoke(
                [
                    "--workspace",
                    str(root),
                    "run",
                    "--name",
                    "cli-demo",
                    "--cwd",
                    str(root),
                    "--metrics",
                    "m.json",
                    "--quiet",
                    "--",
                    sys.executable,
                    "-c",
                    script,
                ]
            )
            self.assertEqual(code, 0)
            run_id = stderr.split("benchlog run ", 1)[1].split(":", 1)[0]

            code, output, _ = self.invoke(["--workspace", str(root), "show", run_id, "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output)["metrics"], {"score": 0.75})

            code, output, _ = self.invoke(["--workspace", str(root), "list", "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output)[0]["name"], "cli-demo")

            code, output, _ = self.invoke(
                ["--workspace", str(root), "compare", run_id, "--format", "csv"]
            )
            self.assertEqual(code, 0)
            self.assertIn("score", output)

            code, output, _ = self.invoke(["--workspace", str(root), "verify", run_id])
            self.assertEqual(code, 0)
            self.assertIn("match", output)

    def test_child_exit_code_is_cli_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.invoke(["init", str(root)])
            code, _, _ = self.invoke(
                [
                    "--workspace",
                    str(root),
                    "run",
                    "--name",
                    "failure",
                    "--cwd",
                    str(root),
                    "--quiet",
                    "--",
                    sys.executable,
                    "-c",
                    "raise SystemExit(9)",
                ]
            )
            self.assertEqual(code, 9)

    def test_doctor_reports_missing_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code, output, _ = self.invoke(["--workspace", directory, "doctor"])
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(output)["workspace_ok"])


if __name__ == "__main__":
    unittest.main()
