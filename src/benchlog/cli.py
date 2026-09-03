"""Command-line interface for BenchLog."""

from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .models import RunRecord
from .query import metric_matrix, recover_run, select_runs, verify_all, verify_run
from .runner import RunRequest, run_command
from .storage import BenchLogError, get_workspace, init_workspace, load_run

STATUSES = ("running", "succeeded", "failed", "timed_out", "interrupted", "error")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="benchlog",
        description="Run commands with reproducible local experiment records.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--workspace",
        type=Path,
        help="project root containing .benchlog (default: discover from current directory)",
    )
    commands = parser.add_subparsers(dest="action", required=True)

    init = commands.add_parser("init", help="initialize a BenchLog workspace")
    init.add_argument("path", nargs="?", type=Path, default=Path.cwd())

    run = commands.add_parser("run", help="execute and record a command")
    run.add_argument("--name", required=True, help="short experiment name")
    run.add_argument("--cwd", type=Path, default=Path.cwd(), help="command working directory")
    run.add_argument("--config", type=Path, help="JSON configuration to snapshot before execution")
    run.add_argument("--metrics", type=Path, help="JSON metrics to collect after execution")
    run.add_argument(
        "--artifact", action="append", type=Path, default=[], help="file to collect after execution"
    )
    run.add_argument("--tag", action="append", default=[], help="searchable tag (repeatable)")
    run.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME",
        help="environment variable to record by name (repeatable)",
    )
    run.add_argument("--timeout", type=float, help="stop the command after this many seconds")
    run.add_argument("--quiet", action="store_true", help="capture child output without echoing it")
    run.add_argument("command", nargs=argparse.REMAINDER, help="command, normally preceded by --")

    listing = commands.add_parser("list", help="list recorded runs")
    listing.add_argument("--status", choices=STATUSES)
    listing.add_argument("--tag")
    listing.add_argument("--limit", type=int)
    listing.add_argument("--json", action="store_true")

    show = commands.add_parser("show", help="show one run manifest")
    show.add_argument("run")
    show.add_argument("--json", action="store_true")

    compare = commands.add_parser("compare", help="compare metrics across runs")
    compare.add_argument("runs", nargs="+")
    compare.add_argument("--metric", action="append", default=[])
    compare.add_argument("--format", choices=("table", "json", "csv"), default="table")

    verify = commands.add_parser("verify", help="verify captured file hashes")
    verify.add_argument("run", nargs="?")
    verify.add_argument("--json", action="store_true")

    recover = commands.add_parser("recover", help="seal an abandoned running manifest")
    recover.add_argument("run")
    recover.add_argument("--reason", default="recovered after interrupted BenchLog process")

    commands.add_parser("doctor", help="check the local installation and workspace")
    return parser


def _table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))
    rendered = ["  ".join(value.ljust(widths[index]) for index, value in enumerate(headers))]
    rendered.append("  ".join("-" * width for width in widths))
    rendered.extend(
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row)) for row in rows
    )
    return "\n".join(rendered)


def _run_summary(record: RunRecord) -> list[str]:
    return [
        record.run_id,
        record.name,
        record.status,
        "" if record.exit_code is None else str(record.exit_code),
        record.started_at,
        ",".join(record.tags),
    ]


def _show_text(record: RunRecord) -> str:
    lines = [
        f"run:       {record.run_id}",
        f"name:      {record.name}",
        f"status:    {record.status}",
        f"command:   {json.dumps(record.command)}",
        f"cwd:       {record.cwd}",
        f"started:   {record.started_at}",
        f"finished:  {record.finished_at or '-'}",
        f"duration:  {record.duration_seconds if record.duration_seconds is not None else '-'}",
        f"exit code: {record.exit_code if record.exit_code is not None else '-'}",
        f"tags:      {', '.join(record.tags) or '-'}",
    ]
    if record.metrics:
        lines.append("metrics:")
        lines.extend(f"  {name}: {value:.12g}" for name, value in sorted(record.metrics.items()))
    if record.error:
        lines.append(f"error:     {record.error}")
    return "\n".join(lines)


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def _command_exit(record: RunRecord) -> int:
    return record.exit_code if record.exit_code is not None and 0 <= record.exit_code <= 255 else 1


def _main(arguments: Sequence[str]) -> int:
    parser = _parser()
    options = parser.parse_args(arguments)

    if options.action == "init":
        store = init_workspace(options.path)
        print(f"Initialized BenchLog workspace at {store}")
        return 0

    if options.action == "doctor":
        checks: dict[str, Any] = {
            "benchlog_version": __version__,
            "python": sys.version.split()[0],
            "git": shutil.which("git"),
        }
        try:
            checks["workspace"] = str(get_workspace(options.workspace))
            checks["workspace_ok"] = True
        except BenchLogError as error:
            checks["workspace"] = str(error)
            checks["workspace_ok"] = False
        print(_json(checks))
        return 0 if checks["workspace_ok"] else 1

    store = get_workspace(options.workspace)
    if options.action == "run":
        command = list(options.command)
        if command[:1] == ["--"]:
            command = command[1:]
        record = run_command(
            RunRequest(
                store=store,
                name=options.name,
                command=command,
                cwd=options.cwd,
                config=options.config,
                metrics=options.metrics,
                artifacts=options.artifact,
                tags=options.tag,
                environment_names=options.env,
                timeout_seconds=options.timeout,
                quiet=options.quiet,
            )
        )
        print(f"benchlog run {record.run_id}: {record.status}", file=sys.stderr)
        return _command_exit(record)

    if options.action == "list":
        if options.limit is not None and options.limit < 1:
            raise BenchLogError("--limit must be at least 1")
        records = select_runs(store, status=options.status, tag=options.tag, limit=options.limit)
        if options.json:
            print(_json([record.to_dict() for record in records]))
        else:
            headers = ["run_id", "name", "status", "exit", "started", "tags"]
            print(_table(headers, [_run_summary(record) for record in records]))
        return 0

    if options.action == "show":
        record = load_run(store, options.run)
        print(_json(record.to_dict()) if options.json else _show_text(record))
        return 0

    if options.action == "compare":
        records = [load_run(store, identifier) for identifier in options.runs]
        headers, rows = metric_matrix(records, options.metric or None)
        if options.format == "table":
            print(_table(headers, rows))
        elif options.format == "json":
            print(_json([dict(zip(headers, row, strict=True)) for row in rows]))
        else:
            buffer = io.StringIO()
            writer = csv.writer(buffer, lineterminator="\n")
            writer.writerow(headers)
            writer.writerows(rows)
            print(buffer.getvalue(), end="")
        return 0

    if options.action == "verify":
        issues = verify_run(store, options.run) if options.run else verify_all(store)
        if options.json:
            print(_json([issue.__dict__ for issue in issues]))
        elif issues:
            for issue in issues:
                print(f"{issue.run_id}  {issue.path}  {issue.problem}")
        else:
            print("All captured files match their manifests.")
        return 1 if issues else 0

    if options.action == "recover":
        record = recover_run(store, options.run, options.reason)
        print(f"Recovered {record.run_id} as interrupted.")
        return 0

    parser.error("unknown command")
    return 2


def main(arguments: Sequence[str] | None = None) -> int:
    """CLI entry point with concise, stable errors."""

    try:
        return _main(sys.argv[1:] if arguments is None else arguments)
    except BenchLogError as error:
        print(f"benchlog: error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
