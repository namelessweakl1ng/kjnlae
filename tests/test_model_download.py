"""Offline tests for the public model download/install boundary."""

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from kjnlae.classifiers.artifacts import BASE_REVISION
from kjnlae.classifiers.download import download_verified_model


def _source_files() -> dict[str, bytes]:
    files = {
        "config.json": json.dumps(
            {"id2label": {"0": "NON_INJECTION", "1": "INJECTION"}}
        ).encode(),
        "tokenizer.json": b"{}",
        "model.safetensors": b"synthetic test-only bytes",
    }
    manifest = {
        "base_revision": BASE_REVISION,
        "trained_steps": 462,
        "artifact_version": "test-v3",
        "evaluated": True,
        "quality_status": "EXPERIMENTAL",
        "threshold": 0.025,
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    }
    files["manifest.json"] = json.dumps(manifest, sort_keys=True).encode()
    return files


def _fake_hub(monkeypatch: pytest.MonkeyPatch, files: dict[str, bytes]) -> None:
    def download_file(*, filename: str, local_dir: Path, **kwargs: object) -> str:
        assert kwargs["token"] is False
        path = local_dir / filename
        path.write_bytes(files[filename])
        return str(path)

    def download_snapshot(
        *, allow_patterns: list[str], local_dir: Path, **kwargs: object
    ) -> str:
        assert kwargs["token"] is False
        for filename in allow_patterns:
            (local_dir / filename).write_bytes(files[filename])
        return str(local_dir)

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(hf_hub_download=download_file, snapshot_download=download_snapshot),
    )


def test_model_download_pins_hash_and_installs_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = _source_files()
    _fake_hub(monkeypatch, files)
    expected = hashlib.sha256(files["manifest.json"]).hexdigest()
    destination = tmp_path / "model"
    artifact = download_verified_model(
        "example/kjnlae", destination, revision="abc123", manifest_sha256=expected
    )
    assert artifact.path == destination
    assert artifact.sha256 == expected
    assert artifact.quality_status == "EXPERIMENTAL"
    assert (destination / "model.safetensors").read_bytes() == files["model.safetensors"]
    assert not list(tmp_path.glob(".kjnlae-model-*"))


def test_model_download_rejects_unexpected_hash_without_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_hub(monkeypatch, _source_files())
    destination = tmp_path / "model"
    with pytest.raises(ValueError, match="SHA-256"):
        download_verified_model("example/kjnlae", destination, manifest_sha256="0" * 64)
    assert not destination.exists()
    assert not list(tmp_path.glob(".kjnlae-model-*"))


def test_model_download_refuses_overwriting_existing_install(tmp_path: Path) -> None:
    destination = tmp_path / "model"
    destination.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        download_verified_model("example/kjnlae", destination)
    assert destination.is_dir()


def test_model_download_rejects_unsafe_file_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = _source_files()
    manifest = json.loads(files["manifest.json"])
    manifest["files"]["../../private.json"] = "a" * 64
    files["manifest.json"] = json.dumps(manifest).encode()
    _fake_hub(monkeypatch, files)
    expected = hashlib.sha256(files["manifest.json"]).hexdigest()
    with pytest.raises(ValueError, match="Unsafe"):
        download_verified_model("example/kjnlae", tmp_path / "model", manifest_sha256=expected)
    assert not (tmp_path / "model").exists()
