"""Preserve pytest failure details in public CI annotations."""

import subprocess
import sys


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode:
        lines = result.stdout.splitlines() + result.stderr.splitlines()
        details = [line for line in lines if line.startswith(("FAILED ", "ERROR ", "E   "))]
        for line in details[:8]:
            escaped = line.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print(f"::error title=pytest failure::{escaped}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
