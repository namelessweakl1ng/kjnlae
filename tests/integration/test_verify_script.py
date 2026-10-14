import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform == "win32", reason="Release script requires POSIX Bash")
def test_release_gate_rejects_missing_artifact():
    root = Path(__file__).resolve().parents[2]
    environment = dict(os.environ)
    environment.pop("KJNLAE_TEST_MODEL_DIR", None)
    environment.pop("KJNLAE_TEST_MODEL_HASH", None)
    environment["KJNLAE_VERIFY_RELEASE"] = "1"
    result = subprocess.run(
        ["bash", "scripts/verify_all.sh"], cwd=root, env=environment, capture_output=True, text=True
    )
    assert result.returncode == 2
    assert "requires KJNLAE_TEST_MODEL_DIR" in result.stderr
