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
    dev_dir = _development_manifest(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_release.py",
            "--cases",
            str(cases),
            "--sha256",
            hashlib.sha256(cases.read_bytes()).hexdigest(),
            "--development-dir",
            str(dev_dir),
            "--development-manifest-sha256",
            hashlib.sha256((dev_dir / "manifest.json").read_bytes()).hexdigest(),
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


def _development_manifest(tmp_path):
    dev_dir = tmp_path / "development"
    dev_dir.mkdir()
    hashes = {}
    for split in ("TRAIN", "VALIDATION", "CALIBRATION"):
        path = dev_dir / f"{split.lower()}.jsonl"
        path.write_text(
            json.dumps(
                {
                    "id": split.lower(),
                    "family_id": split.lower(),
                    "text": f"A separate {split.lower()} reference passage.",
                    "split": split,
                }
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        hashes[split] = hashlib.sha256(path.read_bytes()).hexdigest()
    (dev_dir / "manifest.json").write_text(
        json.dumps({"sha256": hashes, "counts": {key: 1 for key in hashes}}),
        encoding="utf-8",
        newline="\n",
    )
    return dev_dir


def test_release_cli_rejects_final_case_overlapping_verified_development(tmp_path):
    root = Path(__file__).resolve().parents[2]
    dev_dir = _development_manifest(tmp_path)
    cases = tmp_path / "overlap.jsonl"
    cases.write_text(
        json.dumps(
            {
                "id": "final",
                "family_id": "train",
                "text": "An unrelated final passage.",
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
    output = tmp_path / "should-not-exist.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_release.py",
            "--cases",
            str(cases),
            "--sha256",
            hashlib.sha256(cases.read_bytes()).hexdigest(),
            "--development-dir",
            str(dev_dir),
            "--development-manifest-sha256",
            hashlib.sha256((dev_dir / "manifest.json").read_bytes()).hexdigest(),
            "--model-dir",
            str(tmp_path / "missing"),
            "--model-hash",
            "0" * 64,
            "--output",
            str(output),
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "family" in result.stderr.lower()
    assert not output.exists()
