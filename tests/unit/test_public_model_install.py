import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from kjnlae.classifiers.artifacts import (
    PUBLIC_MODEL_MANIFEST_SHA256,
    default_model_dir,
    download_onnx_model,
    download_public_model,
)


def test_default_model_location_is_not_a_working_directory(monkeypatch, tmp_path):
    monkeypatch.setattr("kjnlae.classifiers.artifacts.sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert default_model_dir() == tmp_path / "kjnlae" / "models" / "reviewed-v0.2-onnx"


def test_windows_data_location_uses_local_app_data(monkeypatch, tmp_path):
    monkeypatch.setattr("kjnlae.classifiers.artifacts.sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert default_model_dir() == tmp_path / "kjnlae" / "models" / "reviewed-v0.2-onnx"


def test_macos_data_location_uses_application_support(monkeypatch, tmp_path):
    monkeypatch.setattr("kjnlae.classifiers.artifacts.sys.platform", "darwin")
    monkeypatch.setattr("kjnlae.classifiers.artifacts.Path.home", lambda: tmp_path)
    assert (
        default_model_dir()
        == tmp_path / "Library" / "Application Support" / "kjnlae" / "models" / "reviewed-v0.2-onnx"
    )


def test_download_is_pinned_and_refuses_overwrite(monkeypatch, tmp_path):
    calls = []

    def fake_download(**kwargs):
        calls.append(kwargs)
        directory = Path(kwargs["local_dir"])
        directory.joinpath("manifest.json").write_text("invalid", encoding="utf-8", newline="\n")
        return str(directory)

    monkeypatch.setitem(
        sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=fake_download)
    )
    target = tmp_path / "installed"
    with pytest.raises(ValueError, match="hash"):
        download_public_model(target)
    assert not target.exists()
    assert calls[0]["revision"]
    assert calls[0]["allow_patterns"] == [
        "manifest.json",
        "config.json",
        "model.safetensors",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.txt",
    ]
    assert len(PUBLIC_MODEL_MANIFEST_SHA256) == 64
    target.mkdir()
    with pytest.raises(FileExistsError):
        download_public_model(target)
    assert len(calls) == 1


def test_failed_onnx_download_cleans_staging_without_overwriting(monkeypatch, tmp_path):
    def interrupted(**_kwargs):
        raise ConnectionError("interrupted")

    monkeypatch.setitem(
        sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=interrupted)
    )
    destination = tmp_path / "reviewed-v0.2-onnx"
    with pytest.raises(ConnectionError, match="interrupted"):
        download_onnx_model(destination)
    assert not destination.exists()
    assert list(tmp_path.iterdir()) == []
    destination.mkdir()
    with pytest.raises(FileExistsError):
        download_onnx_model(destination)
