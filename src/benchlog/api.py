"""Small public library API for embedding BenchLog in Python workflows."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from .models import RunRecord
from .query import select_runs, verify_run
from .runner import RunRequest, run_command
from .storage import get_workspace, init_workspace, load_run


class BenchLog:
    """A handle to one local BenchLog workspace."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.store = get_workspace(Path(root) if root is not None else None)

    @classmethod
    def initialize(cls, root: str | Path) -> BenchLog:
        """Initialize *root* and return an open handle."""

        root_path = Path(root)
        init_workspace(root_path)
        return cls(root_path)

    def run(
        self,
        name: str,
        command: Sequence[str],
        *,
        cwd: str | Path | None = None,
        config: str | Path | None = None,
        metrics: str | Path | None = None,
        artifacts: Sequence[str | Path] = (),
        tags: Sequence[str] = (),
        environment_names: Sequence[str] = (),
        timeout_seconds: float | None = None,
        quiet: bool = False,
    ) -> RunRecord:
        """Run a command and return its persisted record."""

        request = RunRequest(
            store=self.store,
            name=name,
            command=list(command),
            cwd=Path(cwd) if cwd is not None else Path.cwd(),
            config=Path(config) if config is not None else None,
            metrics=Path(metrics) if metrics is not None else None,
            artifacts=[Path(item) for item in artifacts],
            tags=list(tags),
            environment_names=list(environment_names),
            timeout_seconds=timeout_seconds,
            quiet=quiet,
        )
        return run_command(request)

    def get(self, identifier: str) -> RunRecord:
        """Load a run by full ID or unique prefix."""

        return load_run(self.store, identifier)

    def runs(
        self,
        *,
        status: str | None = None,
        tag: str | None = None,
        limit: int | None = None,
    ) -> list[RunRecord]:
        """List runs, newest first."""

        return select_runs(self.store, status=status, tag=tag, limit=limit)

    def verify(self, identifier: str) -> bool:
        """Return whether all captured files for a run match its manifest."""

        return not verify_run(self.store, identifier)
