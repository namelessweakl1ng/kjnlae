import hashlib
import json
from pathlib import Path

import pytest

from kjnlae.classifiers.artifacts import verify_artifact


def _artifact(path: Path) -> str:
    path.mkdir()
    files = {
        "model.safetensors": b"synthetic-test-bytes",
        "tokenizer.json": b"{}",
        "config.json": json.dumps({"id2label": {"0": "NON_INJECTION", "1": "INJECTION"}}).encode(),
    }
    for name, content in files.items():
        (path / name).write_bytes(content)
    manifest = {
        "artifact_version": "test-v2",
        "base_revision": "12040accade4e8a0f71eabdb258fecc2e7e948be",
        "trained_steps": 10,
        "approved": True,
        "threshold": 0.7,
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
    }
    (path / "manifest.json").write_text(json.dumps(manifest))
    return hashlib.sha256((path / "manifest.json").read_bytes()).hexdigest()


def test_verified_artifact_checks_pinned_hash_and_files(tmp_path: Path) -> None:
    expected = _artifact(tmp_path / "model")
    artifact = verify_artifact(tmp_path / "model", expected)
    assert artifact.sha256 == expected
    (tmp_path / "model" / "model.safetensors").write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash"):
        verify_artifact(tmp_path / "model", expected)


def test_untrained_or_symlink_artifacts_are_rejected(tmp_path: Path) -> None:
    expected = _artifact(tmp_path / "model")
    manifest_path = tmp_path / "model" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["trained_steps"] = 0
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="trained"):
        verify_artifact(tmp_path / "model", None)
    (tmp_path / "model" / "tokenizer.json").unlink()
    (tmp_path / "model" / "tokenizer.json").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError):
        verify_artifact(tmp_path / "model", expected)
