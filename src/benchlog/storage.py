"""Filesystem storage with atomic manifest updates."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import RunRecord

STORE_NAME = ".benchlog"
STORE_VERSION = "1\n"


class BenchLogError(Exception):
    """A user-facing BenchLog error."""


def _secure_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix":
        path.chmod(0o700)


def _secure_file(path: Path) -> None:
    if os.name == "posix":
        path.chmod(0o600)


def init_workspace(root: Path) -> Path:
    """Create and return the metadata directory below *root*."""

    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    store = root / STORE_NAME
    _secure_directory(store)
    _secure_directory(store / "runs")
    version = store / "VERSION"
    if not version.exists():
        version.write_text(STORE_VERSION, encoding="utf-8")
        _secure_file(version)
    elif version.read_text(encoding="utf-8") != STORE_VERSION:
        raise BenchLogError(f"unsupported store version in {version}")
    return store


def find_workspace(start: Path | None = None) -> Path:
    """Find the nearest initialized metadata directory."""

    current = (start or Path.cwd()).expanduser().resolve()
    if current.name == STORE_NAME and (current / "VERSION").is_file():
        return current
    for candidate in (current, *current.parents):
        store = candidate / STORE_NAME
        if (store / "VERSION").is_file():
            return store
    raise BenchLogError("no BenchLog workspace found; run `benchlog init` first")


def get_workspace(root: Path | None) -> Path:
    """Resolve an explicit project root or discover one from the current directory."""

    if root is None:
        return find_workspace()
    candidate = root.expanduser().resolve()
    store = candidate if candidate.name == STORE_NAME else candidate / STORE_NAME
    if not (store / "VERSION").is_file():
        raise BenchLogError(f"{candidate} is not initialized; run `benchlog init {candidate}`")
    return store


def atomic_write_json(path: Path, value: Any) -> None:
    """Atomically replace a JSON file with owner-only permissions."""

    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _secure_file(temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def new_run_directory(store: Path) -> tuple[str, Path]:
    """Create a collision-resistant run directory."""

    for _ in range(10):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        run_id = f"{stamp}-{secrets.token_hex(3)}"
        target = store / "runs" / run_id
        try:
            target.mkdir(mode=0o700)
        except FileExistsError:
            continue
        _secure_directory(target / "artifacts")
        return run_id, target
    raise BenchLogError("could not allocate a unique run identifier")


def save_run(store: Path, record: RunRecord) -> None:
    """Persist a run manifest atomically."""

    target = store / "runs" / record.run_id / "manifest.json"
    if not target.parent.is_dir():
        raise BenchLogError(f"run directory is missing: {record.run_id}")
    atomic_write_json(target, record.to_dict())


def load_run(store: Path, identifier: str) -> RunRecord:
    """Load a run by exact identifier or unique prefix."""

    run_id = resolve_run_id(store, identifier)
    manifest = store / "runs" / run_id / "manifest.json"
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BenchLogError(f"cannot read manifest for {run_id}: {error}") from error
    if not isinstance(value, dict):
        raise BenchLogError(f"manifest for {run_id} is not a JSON object")
    try:
        return RunRecord.from_dict(value)
    except (TypeError, ValueError) as error:
        raise BenchLogError(f"manifest for {run_id} is invalid: {error}") from error


def resolve_run_id(store: Path, identifier: str) -> str:
    """Resolve a full run ID or unambiguous prefix."""

    if not identifier or "/" in identifier or "\\" in identifier:
        raise BenchLogError("invalid run identifier")
    exact = store / "runs" / identifier
    if (exact / "manifest.json").is_file():
        return identifier
    matches = sorted(
        path.name
        for path in (store / "runs").iterdir()
        if path.is_dir() and path.name.startswith(identifier) and (path / "manifest.json").is_file()
    )
    if not matches:
        raise BenchLogError(f"run not found: {identifier}")
    if len(matches) > 1:
        raise BenchLogError(f"ambiguous run prefix {identifier!r}; matched {len(matches)} runs")
    return matches[0]


def iter_runs(store: Path) -> Iterator[RunRecord]:
    """Yield valid run manifests newest first."""

    paths = sorted((store / "runs").glob("*/manifest.json"), reverse=True)
    for path in paths:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                yield RunRecord.from_dict(value)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file without loading it all into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_metadata(path: Path) -> tuple[str, int]:
    """Return digest and size for a regular file."""

    if not path.is_file():
        raise BenchLogError(f"not a regular file: {path}")
    return sha256_file(path), path.stat().st_size
