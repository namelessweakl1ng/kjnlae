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
        "evaluated": True,
        "quality_status": "EXPERIMENTAL",
        "threshold": 0.7,
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
    }
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8", newline="\n")
    return hashlib.sha256((path / "manifest.json").read_bytes()).hexdigest()


def test_verified_artifact_checks_pinned_hash_and_files(tmp_path: Path) -> None:
    expected = _artifact(tmp_path / "model")
    artifact = verify_artifact(tmp_path / "model", expected)
    assert artifact.sha256 == expected
    assert artifact.quality_status == "EXPERIMENTAL"
    (tmp_path / "model" / "model.safetensors").write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash"):
        verify_artifact(tmp_path / "model", expected)


def test_untrained_or_symlink_artifacts_are_rejected(tmp_path: Path) -> None:
    expected = _artifact(tmp_path / "model")
    manifest_path = tmp_path / "model" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["trained_steps"] = 0
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match="trained"):
        verify_artifact(tmp_path / "model", None)
    (tmp_path / "model" / "tokenizer.json").unlink()
    (tmp_path / "model" / "tokenizer.json").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError):
        verify_artifact(tmp_path / "model", expected)


def test_evaluated_artifact_requires_explicit_experimental_status(tmp_path: Path) -> None:
    _artifact(tmp_path / "model")
    manifest_path = tmp_path / "model" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert verify_artifact(tmp_path / "model", None).quality_status == "EXPERIMENTAL"
    del manifest["quality_status"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match="quality status"):
        verify_artifact(tmp_path / "model", None)


@pytest.mark.parametrize("threshold", [0, -0.1, 1.1, True])
def test_invalid_calibration_threshold_is_rejected(tmp_path: Path, threshold: object) -> None:
    """No approved artifact may produce a threshold that the policy cannot use."""
    _artifact(tmp_path / "model")
    path = tmp_path / "model" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["threshold"] = threshold
    path.write_text(json.dumps(manifest), encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match="calibration threshold"):
        verify_artifact(tmp_path / "model", None)
