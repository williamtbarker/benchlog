"""Tracked subprocess execution."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

from .models import FileRecord, RunRecord
from .provenance import flatten_metrics, git_state, read_json, system_environment
from .storage import BenchLogError, file_metadata, new_run_directory, save_run


@dataclass(frozen=True)
class RunRequest:
    """Inputs for a tracked command."""

    store: Path
    name: str
    command: list[str]
    cwd: Path
    config: Path | None = None
    metrics: Path | None = None
    artifacts: list[Path] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    environment_names: list[str] = field(default_factory=list)
    timeout_seconds: float | None = None
    quiet: bool = False


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _add_file(
    record: RunRecord,
    run_directory: Path,
    relative_path: str,
    role: str,
    source: Path | None = None,
) -> None:
    path = run_directory / relative_path
    digest, size = file_metadata(path)
    record.files = [item for item in record.files if item.path != relative_path]
    record.files.append(
        FileRecord(
            path=relative_path,
            role=role,
            sha256=digest,
            size=size,
            source=str(source) if source is not None else None,
        )
    )


def _copy_input(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise BenchLogError(f"not a regular file: {source}")
    shutil.copyfile(source, destination)
    if os.name == "posix":
        destination.chmod(0o600)


def _pump(stream: TextIO, log: TextIO, terminal: TextIO | None) -> None:
    try:
        for line in stream:
            log.write(line)
            log.flush()
            if terminal is not None:
                terminal.write(line)
                terminal.flush()
    finally:
        stream.close()


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except OSError:
            pass
        process.wait()


def _artifact_name(source: Path, used: set[str]) -> str:
    base = source.name or "artifact"
    candidate = base
    counter = 2
    while candidate in used:
        candidate = f"{source.stem}-{counter}{source.suffix}"
        counter += 1
    used.add(candidate)
    return candidate


def run_command(request: RunRequest) -> RunRecord:
    """Execute a command and persist its run record."""

    if not request.name.strip():
        raise BenchLogError("run name cannot be empty")
    if not request.command:
        raise BenchLogError("no command supplied after `--`")
    cwd = request.cwd.expanduser().resolve()
    if not cwd.is_dir():
        raise BenchLogError(f"working directory does not exist: {cwd}")
    if request.timeout_seconds is not None and request.timeout_seconds <= 0:
        raise BenchLogError("timeout must be greater than zero")

    config_source = request.config
    config_value = None
    if config_source is not None:
        config_source = (
            (cwd / config_source).resolve()
            if not config_source.is_absolute()
            else config_source.resolve()
        )
        config_value = read_json(config_source, label="config")

    environment = system_environment(request.environment_names)
    run_id, run_directory = new_run_directory(request.store)
    record = RunRecord(
        run_id=run_id,
        name=request.name.strip(),
        status="running",
        command=request.command,
        cwd=str(cwd),
        started_at=utc_now(),
        timeout_seconds=request.timeout_seconds,
        tags=sorted(set(request.tags)),
        config=config_value,
        environment=environment,
        git=git_state(cwd),
    )

    if config_source is not None:
        destination = run_directory / "config.json"
        _copy_input(config_source, destination)
        _add_file(record, run_directory, "config.json", "config", config_source)
    save_run(request.store, record)

    stdout_path = run_directory / "stdout.log"
    stderr_path = run_directory / "stderr.log"
    start = time.monotonic()
    process: subprocess.Popen[str] | None = None
    interrupted = False
    timed_out = False
    launch_error: OSError | None = None

    with (
        stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_log,
        stderr_path.open("w", encoding="utf-8", errors="replace") as stderr_log,
    ):
        if os.name == "posix":
            stdout_path.chmod(0o600)
            stderr_path.chmod(0o600)
        try:
            process = subprocess.Popen(
                request.command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                start_new_session=os.name == "posix",
            )
            record.pid = process.pid
            save_run(request.store, record)
            assert process.stdout is not None
            assert process.stderr is not None
            stdout_thread = threading.Thread(
                target=_pump,
                args=(process.stdout, stdout_log, None if request.quiet else sys.stdout),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=_pump,
                args=(process.stderr, stderr_log, None if request.quiet else sys.stderr),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()
            try:
                process.wait(timeout=request.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                _stop_process(process)
            except KeyboardInterrupt:
                interrupted = True
                _stop_process(process)
            stdout_thread.join()
            stderr_thread.join()
        except OSError as error:
            launch_error = error
            stderr_log.write(f"benchlog: could not start command: {error}\n")

    record.duration_seconds = round(time.monotonic() - start, 6)
    record.finished_at = utc_now()
    record.pid = None
    _add_file(record, run_directory, "stdout.log", "stdout")
    _add_file(record, run_directory, "stderr.log", "stderr")

    if launch_error is not None:
        record.status = "failed"
        record.exit_code = 127 if isinstance(launch_error, FileNotFoundError) else 126
        record.error = str(launch_error)
    elif timed_out:
        record.status = "timed_out"
        record.exit_code = 124
        record.error = f"command exceeded {request.timeout_seconds:g} seconds"
    elif interrupted:
        record.status = "interrupted"
        record.exit_code = 130
        record.error = "interrupted by user"
    else:
        assert process is not None
        raw_code = process.returncode
        record.exit_code = 128 + abs(raw_code) if raw_code < 0 else raw_code
        record.status = "succeeded" if raw_code == 0 else "failed"

    try:
        if request.metrics is not None:
            metrics_source = (
                (cwd / request.metrics).resolve()
                if not request.metrics.is_absolute()
                else request.metrics.resolve()
            )
            metric_value = read_json(metrics_source, label="metrics")
            record.metrics = flatten_metrics(metric_value)
            destination = run_directory / "metrics.json"
            _copy_input(metrics_source, destination)
            _add_file(record, run_directory, "metrics.json", "metrics", metrics_source)

        used: set[str] = set()
        for artifact in request.artifacts:
            source = (
                (cwd / artifact).resolve() if not artifact.is_absolute() else artifact.resolve()
            )
            name = _artifact_name(source, used)
            destination = run_directory / "artifacts" / name
            _copy_input(source, destination)
            _add_file(record, run_directory, f"artifacts/{name}", "artifact", source)
    except BenchLogError as error:
        record.status = "error"
        record.exit_code = 2
        record.error = str(error)

    record.files.sort(key=lambda item: item.path)
    save_run(request.store, record)
    return record
