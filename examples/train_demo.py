#!/usr/bin/env python3
"""Deterministic dependency-free training stand-in for the BenchLog demo."""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    arguments = parser.parse_args()

    config: dict[str, Any] = json.loads(arguments.config.read_text(encoding="utf-8"))
    seed = int(config["seed"])
    epochs = int(config["epochs"])
    learning_rate = float(config["learning_rate"])
    random_source = random.Random(seed)

    loss = 1.0
    for epoch in range(1, epochs + 1):
        loss *= 1.0 - min(0.4, learning_rate * 10)
        loss += random_source.uniform(-0.005, 0.005)
        print(f"epoch={epoch} loss={loss:.6f}")

    accuracy = min(0.999, 1.0 - max(0.0, loss) / 2)
    metrics = {
        "test": {"accuracy": accuracy, "loss": max(0.0, loss)},
        "training": {"epochs": epochs},
    }
    arguments.metrics.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    model = {
        "format": "benchlog-demo-model-v1",
        "seed": seed,
        "weight": round(math.cos(seed) * accuracy, 12),
    }
    arguments.model.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
