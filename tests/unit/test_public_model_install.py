from pathlib import Path

import pytest

from kjnlae.classifiers.artifacts import (
    PUBLIC_MODEL_MANIFEST_SHA256,
    default_model_dir,
    download_public_model,
)


def test_default_model_location_is_not_a_working_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert default_model_dir() == tmp_path / "kjnlae" / "models" / "reviewed-v0.2"


def test_download_is_pinned_and_refuses_overwrite(monkeypatch, tmp_path):
    calls = []

    def fake_download(**kwargs):
        calls.append(kwargs)
        directory = Path(kwargs["local_dir"])
        directory.joinpath("manifest.json").write_text("invalid")
        return str(directory)

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake_download)
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
