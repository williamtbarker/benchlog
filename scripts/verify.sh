#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -n "${PYTHON_BIN:-}" ]]; then
  python_bin="$PYTHON_BIN"
elif [[ -x "$project_root/.venv/bin/python" ]]; then
  python_bin="$project_root/.venv/bin/python"
else
  python_bin="python3"
fi
demo_root="$(mktemp -d)"

cleanup() {
  if [[ -n "${demo_root:-}" && -d "$demo_root" ]]; then
    rm -rf -- "$demo_root"
  fi
}
trap cleanup EXIT

cd "$project_root"

"$python_bin" -m compileall -q src examples tests
"$python_bin" -m unittest discover -s tests -v
"$python_bin" -m ruff format --check .
"$python_bin" -m ruff check .
"$python_bin" -m mypy

"$python_bin" -m benchlog init "$demo_root"
cp examples/config.json "$demo_root/config.json"
"$python_bin" -m benchlog --workspace "$demo_root" run \
  --name deterministic-demo \
  --config "$demo_root/config.json" \
  --metrics "$demo_root/metrics.json" \
  --artifact "$demo_root/model.json" \
  --tag demo \
  --quiet \
  -- "$python_bin" "$project_root/examples/train_demo.py" \
  --config "$demo_root/config.json" \
  --metrics "$demo_root/metrics.json" \
  --model "$demo_root/model.json"
"$python_bin" -m benchlog --workspace "$demo_root" verify
"$python_bin" -m benchlog --workspace "$demo_root" list --json > "$demo_root/runs.json"
"$python_bin" - "$demo_root/runs.json" <<'PY'
import json
import sys

runs = json.load(open(sys.argv[1], encoding="utf-8"))
assert len(runs) == 1
assert runs[0]["status"] == "succeeded"
assert "test.accuracy" in runs[0]["metrics"]
assert any(item["role"] == "artifact" for item in runs[0]["files"])
PY

"$python_bin" -m build
"$python_bin" -m venv "$demo_root/package-venv"
"$demo_root/package-venv/bin/python" -m pip install --no-deps dist/benchlog-0.1.0-py3-none-any.whl
"$demo_root/package-venv/bin/benchlog" --version

echo "All checks passed, including the deterministic tracked-run demo."
