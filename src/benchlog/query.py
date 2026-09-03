"""Run discovery, comparison, recovery, and integrity checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import RunRecord
from .storage import BenchLogError, iter_runs, load_run, save_run, sha256_file


@dataclass(frozen=True)
class VerificationIssue:
    """One integrity problem found in a run."""

    run_id: str
    path: str
    problem: str


def select_runs(
    store: Path,
    *,
    status: str | None = None,
    tag: str | None = None,
    limit: int | None = None,
) -> list[RunRecord]:
    """Return runs matching simple metadata filters."""

    selected = [
        run
        for run in iter_runs(store)
        if (status is None or run.status == status) and (tag is None or tag in run.tags)
    ]
    return selected if limit is None else selected[:limit]


def metric_matrix(
    runs: list[RunRecord], metrics: list[str] | None = None
) -> tuple[list[str], list[list[str]]]:
    """Build a deterministic comparison table."""

    names = sorted(set(metrics or []).union(*(run.metrics.keys() for run in runs)))
    rows: list[list[str]] = []
    for run in runs:
        values = [
            format(run.metrics[name], ".12g") if name in run.metrics else "" for name in names
        ]
        rows.append([run.run_id, run.name, run.status, *values])
    return ["run_id", "name", "status", *names], rows


def verify_run(store: Path, identifier: str) -> list[VerificationIssue]:
    """Verify every file registered in a run manifest."""

    record = load_run(store, identifier)
    run_directory = (store / "runs" / record.run_id).resolve()
    issues: list[VerificationIssue] = []
    for item in record.files:
        candidate = (run_directory / item.path).resolve()
        if candidate != run_directory and run_directory not in candidate.parents:
            issues.append(VerificationIssue(record.run_id, item.path, "path escapes run directory"))
            continue
        if not candidate.is_file():
            issues.append(VerificationIssue(record.run_id, item.path, "missing"))
            continue
        if candidate.stat().st_size != item.size:
            issues.append(VerificationIssue(record.run_id, item.path, "size mismatch"))
            continue
        if sha256_file(candidate) != item.sha256:
            issues.append(VerificationIssue(record.run_id, item.path, "SHA-256 mismatch"))
    return issues


def verify_all(store: Path) -> list[VerificationIssue]:
    """Verify every readable run."""

    issues: list[VerificationIssue] = []
    for record in iter_runs(store):
        issues.extend(verify_run(store, record.run_id))
    return issues


def recover_run(store: Path, identifier: str, reason: str) -> RunRecord:
    """Seal a run whose original BenchLog process stopped before finalization."""

    record = load_run(store, identifier)
    if record.status != "running":
        raise BenchLogError(f"run {record.run_id} is {record.status}, not running")
    now = datetime.now(timezone.utc)
    started = datetime.fromisoformat(record.started_at.replace("Z", "+00:00"))
    record.status = "interrupted"
    record.finished_at = now.isoformat().replace("+00:00", "Z")
    record.duration_seconds = round(max(0.0, (now - started).total_seconds()), 6)
    record.exit_code = 130
    record.pid = None
    record.error = reason
    save_run(store, record)
    return record
