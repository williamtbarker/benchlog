"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

from benchlog.runner import RunRequest, run_command
from benchlog.storage import init_workspace


def successful_run(root: Path, name: str = "trial"):
    """Create one tiny successful run."""

    store = init_workspace(root)
    return run_command(
        RunRequest(
            store=store,
            name=name,
            command=["python3", "-c", "print('ok')"],
            cwd=root,
            quiet=True,
        )
    )
