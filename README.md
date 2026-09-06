# BenchLog

[![License](https://img.shields.io/github/license/williamtbarker/benchlog)](https://github.com/williamtbarker/benchlog/blob/main/LICENSE)
[![Release](https://img.shields.io/github/v/release/williamtbarker/benchlog?display_name=tag&sort=semver)](https://github.com/williamtbarker/benchlog/releases)

[![CI](https://github.com/williamtbarker/benchlog/actions/workflows/ci.yml/badge.svg)](https://github.com/williamtbarker/benchlog/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

BenchLog is a local, inspectable experiment tracker for command-line workflows. It runs an
arbitrary command, preserves exactly what happened, and returns the child's exit code. There is no
server, account, database, or runtime dependency.

It is designed for the gap between loose folders named `run_final_2` and a hosted experiment
platform: small enough to understand, but disciplined enough to make comparisons and provenance
useful.

## What it records

- exact argument vector and working directory, without invoking a shell;
- start/end times, duration, PID while active, status, and exit code;
- stdout and stderr in separate logs, with optional live echo;
- a JSON configuration snapshot and flattened numeric metrics;
- explicitly selected artifacts with SHA-256 digests and byte sizes;
- Git commit, branch, and dirty state when run inside a repository;
- Python and platform information;
- only the environment variables explicitly named with `--env`.

Each run is a plain directory under `.benchlog/runs/`. The atomically updated `manifest.json` is
both the source of truth and an ordinary file you can inspect with any editor.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

benchlog init
benchlog run \
  --name baseline \
  --config examples/config.json \
  --metrics metrics.json \
  --artifact model.json \
  --tag transformer \
  -- python examples/train_demo.py \
     --config examples/config.json \
     --metrics metrics.json \
     --model model.json
```

The final options after `--` belong to your program. The metrics and artifact paths are evaluated
after the command finishes, so the command can create them.

Inspect the result:

```bash
benchlog list
benchlog show 20260903T      # unique prefixes are accepted
benchlog verify
```

Run a second configuration, then compare selected metrics:

```bash
benchlog compare RUN_ID_1 RUN_ID_2 --metric test.loss --metric test.accuracy
benchlog compare RUN_ID_1 RUN_ID_2 --format csv > comparison.csv
```

## CLI guide

### Initialize

```bash
benchlog init [PATH]
```

Creates `PATH/.benchlog` (or `.benchlog` in the current directory). Commands launched anywhere
below that directory discover the nearest workspace automatically. Use the global option
`--workspace PATH` to select one explicitly.

### Track a command

```bash
benchlog run --name NAME [OPTIONS] -- COMMAND [ARG ...]
```

Useful options:

| Option | Behavior |
| --- | --- |
| `--config FILE` | Validate and snapshot JSON before launch |
| `--metrics FILE` | Validate, snapshot, and flatten numeric JSON after exit |
| `--artifact FILE` | Copy a result file after exit; repeatable |
| `--tag TAG` | Add a list/search tag; repeatable |
| `--env NAME` | Record one named environment variable; repeatable |
| `--timeout SECONDS` | Terminate an overlong process and return 124 |
| `--cwd PATH` | Set the child's working directory |
| `--quiet` | Capture output without echoing it live |

BenchLog returns the child's exit code for ordinary success and failure. Its own input/storage
errors return 2, a timeout returns 124, and an interrupted run returns 130. A command is always an
argument vector; shell expansion, pipes, and redirection do not happen implicitly. If you actually
need shell syntax, make that choice explicit: `-- bash -lc 'command | command'`.

### Query

```bash
benchlog list --status succeeded --tag baseline --limit 10
benchlog list --json
benchlog show RUN_ID --json
benchlog compare RUN_ID... --format table
```

Nested metrics such as `{"validation": {"loss": 0.125}}` become
`validation.loss`. Metrics must be finite JSON numbers; strings, booleans, `NaN`, and infinities are
rejected so comparisons remain meaningful.

### Verify and recover

```bash
benchlog verify [RUN_ID]
benchlog recover RUN_ID --reason "laptop restarted"
```

`verify` recalculates every registered size and SHA-256 digest. `recover` is deliberately explicit:
it seals a manifest left in `running` state when the original BenchLog process could not finalize
it. It does not resume model training or guess whether an old PID is still valid.

### Diagnose setup

```bash
benchlog doctor
benchlog --workspace /path/to/project doctor
```

## Run layout

```text
.benchlog/
├── VERSION
└── runs/
    └── 20260903T...-a1b2c3/
        ├── manifest.json
        ├── stdout.log
        ├── stderr.log
        ├── config.json
        ├── metrics.json
        └── artifacts/
            └── model.json
```

Captured files are copies, not links. Duplicate artifact basenames are safely disambiguated. The
manifest itself is excluded from its integrity list because its hashes and final status are updated
atomically during the run.

## Python API

```python
from benchlog import BenchLog

log = BenchLog.initialize("experiments")
run = log.run(
    "baseline",
    ["python", "train.py", "--seed", "42"],
    cwd="experiments",
    config="config.json",
    metrics="metrics.json",
    artifacts=["model.bin"],
    tags=["baseline"],
)

print(run.run_id, run.metrics)
assert log.verify(run.run_id)
```

`BenchLog()` without a path discovers the nearest workspace, matching the CLI.

## Design boundaries

BenchLog intentionally does not provide dashboards, remote storage, distributed coordination,
framework callbacks, or training checkpoint resumption. It records a command and its selected
outputs in a transparent local format. Large artifacts are copied in full, so use `--artifact`
selectively.

No automatic secret redaction is possible for arbitrary logs, arguments, configuration, or output
files. Environment capture is opt-in, but you should still review a `.benchlog` directory before
sharing it.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
./scripts/verify.sh
```

The verification gate runs unit and CLI tests, formatting, linting, strict type checking, a complete
tracked-run demo, and source/wheel builds. CI runs the same gate on macOS and Ubuntu with the oldest
and newest supported Python versions.

## License

MIT
