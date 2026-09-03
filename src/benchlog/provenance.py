"""Configuration, metric, environment, and Git provenance helpers."""

from __future__ import annotations

import json
import math
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from .storage import BenchLogError

ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def read_json(path: Path, *, label: str) -> Any:
    """Load JSON and provide a concise diagnostic on failure."""

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise BenchLogError(f"cannot read {label} file {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise BenchLogError(
            f"invalid JSON in {label} file {path} at line {error.lineno}, column {error.colno}"
        ) from error


def flatten_metrics(value: Any) -> dict[str, float]:
    """Flatten a nested JSON object into finite numeric dot-path metrics."""

    if not isinstance(value, dict):
        raise BenchLogError("metrics JSON must contain an object at the top level")
    flattened: dict[str, float] = {}

    def visit(item: Any, prefix: str) -> None:
        if isinstance(item, dict):
            if not item and prefix:
                raise BenchLogError(f"metric group {prefix!r} is empty")
            for key in sorted(item):
                if not isinstance(key, str) or not key:
                    raise BenchLogError("metric names must be non-empty strings")
                visit(item[key], f"{prefix}.{key}" if prefix else key)
            return
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise BenchLogError(f"metric {prefix!r} must be numeric")
        number = float(item)
        if not math.isfinite(number):
            raise BenchLogError(f"metric {prefix!r} must be finite")
        flattened[prefix] = number

    visit(value, "")
    return flattened


def system_environment(names: list[str]) -> dict[str, Any]:
    """Capture platform details and only explicitly requested environment variables."""

    requested: dict[str, str | None] = {}
    for name in names:
        if not ENVIRONMENT_NAME.fullmatch(name):
            raise BenchLogError(f"invalid environment variable name: {name!r}")
        requested[name] = os.environ.get(name)
    return {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "requested_variables": requested,
    }


def git_state(cwd: Path) -> dict[str, Any] | None:
    """Return lightweight Git provenance without recording patches or remotes."""

    def invoke(*arguments: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *arguments],
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    root = invoke("rev-parse", "--show-toplevel")
    commit = invoke("rev-parse", "HEAD")
    if root is None or commit is None:
        return None
    branch = invoke("branch", "--show-current")
    status = invoke("status", "--porcelain", "--untracked-files=normal")
    return {
        "root": root,
        "commit": commit,
        "branch": branch or None,
        "dirty": bool(status),
    }
