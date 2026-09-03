# Contributing

Contributions are welcome through focused issues and pull requests.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
./scripts/verify.sh
```

The verification script runs the unit tests, formatter check, linter, strict type checker,
end-to-end demo, and package build. Add regression tests for behavior changes. Avoid introducing
runtime dependencies unless the standard library cannot provide a clear, robust implementation.
