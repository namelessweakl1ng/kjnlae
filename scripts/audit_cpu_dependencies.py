"""Resolve the plain package in an isolated pip environment and reject GPU stacks."""

import json
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def unexpected_packages(names: list[str]) -> list[str]:
    """Find packages that a CPU-only inference install must never require."""
    blocked = ("nvidia-", "cuda-", "triton", "torch", "transformers")
    return [name for name in names if name.lower().replace("_", "-").startswith(blocked)]


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="kjnlae-resolve-") as name:
        directory = Path(name)
        venv.EnvBuilder(with_pip=True).create(directory / "venv")
        python = (
            directory / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        )
        report = directory / "report.json"
        subprocess.run(
            [str(python), "-m", "pip", "install", "--dry-run", "--report", str(report), str(root)],
            check=True,
            timeout=300,
            stdout=subprocess.DEVNULL,
        )
        names = [
            item["metadata"]["name"]
            for item in json.loads(report.read_text(encoding="utf-8"))["install"]
        ]
        blocked = unexpected_packages(names)
        if blocked:
            raise SystemExit(f"Unexpected GPU/training dependencies: {blocked}")
        print(f"CPU default dependency resolution: {len(names)} packages; no CUDA or torch")


if __name__ == "__main__":
    main()
