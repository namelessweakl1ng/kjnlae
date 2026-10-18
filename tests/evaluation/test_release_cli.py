import hashlib
import json
import subprocess
import sys
from pathlib import Path


def test_release_cli_records_missing_model_as_incomplete(tmp_path):
    root = Path(__file__).resolve().parents[2]
    cases = tmp_path / "cases.jsonl"
    cases.write_text(
        json.dumps(
            {
                "id": "one",
                "family_id": "one",
                "text": "Please summarize this document.",
                "label": 0,
                "source": "user",
                "category": "ordinary",
                "provenance": "original-mit",
            }
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    output = tmp_path / "result.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_release.py",
            "--cases",
            str(cases),
            "--sha256",
            hashlib.sha256(cases.read_bytes()).hexdigest(),
            "--model-dir",
            str(tmp_path / "absent"),
            "--model-hash",
            "0" * 64,
            "--output",
            str(output),
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "INCOMPLETE"
    assert report["metrics"] is None
