"""Serializable records used by BenchLog."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class FileRecord:
    """Integrity metadata for one file stored with a run."""

    path: str
    role: str
    sha256: str
    size: int
    source: str | None = None


@dataclass
class RunRecord:
    """A durable description of one tracked command."""

    run_id: str
    name: str
    status: str
    command: list[str]
    cwd: str
    started_at: str
    finished_at: str | None = None
    duration_seconds: float | None = None
    exit_code: int | None = None
    timeout_seconds: float | None = None
    pid: int | None = None
    tags: list[str] = field(default_factory=list)
    config: Any = None
    metrics: dict[str, float] = field(default_factory=dict)
    files: list[FileRecord] = field(default_factory=list)
    environment: dict[str, Any] = field(default_factory=dict)
    git: dict[str, Any] | None = None
    error: str | None = None
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible mapping."""

        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> RunRecord:
        """Build a record from its persisted representation."""

        data = dict(value)
        data["files"] = [FileRecord(**item) for item in data.get("files", [])]
        return cls(**data)
