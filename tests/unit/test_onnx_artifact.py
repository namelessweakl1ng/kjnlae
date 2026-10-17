import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from kjnlae.classifiers.artifacts import (
    ONNX_MODEL_SHA256,
    ONNX_TEMPLATE_SHA256,
    convert_verified_model,
    verify_onnx_artifact,
)


def test_template_has_no_model_weights():
    import hashlib

    import onnx

    template = Path(__file__).resolve().parents[2] / "src/kjnlae/classifiers/model-template.onnx"
    assert hashlib.sha256(template.read_bytes()).hexdigest() == ONNX_TEMPLATE_SHA256
    graph = onnx.load(template, load_external_data=False)
    assert len(graph.graph.initializer) == 104
    assert all(not entry.raw_data for entry in graph.graph.initializer)


@pytest.mark.model
def test_conversion_of_reviewed_checkpoint_has_pinned_identity(tmp_path):
    source = os.getenv("KJNLAE_TEST_MODEL_DIR")
    if not source:
        pytest.skip("Real reviewed checkpoint required")
    artifact = convert_verified_model(Path(source), tmp_path / "onnx-model")
    assert artifact.path.joinpath("model.onnx").is_file()
    assert artifact.sha256 == verify_onnx_artifact(artifact.path, artifact.sha256).sha256
    import hashlib

    assert (
        hashlib.sha256((artifact.path / "model.onnx").read_bytes()).hexdigest() == ONNX_MODEL_SHA256
    )
    assert not (artifact.path / "model.safetensors").exists()


@pytest.mark.model
def test_onnx_manifest_cannot_change_reviewed_threshold(tmp_path):
    source = os.getenv("KJNLAE_TEST_ONNX_DIR")
    if not source:
        pytest.skip("Verified ONNX artifact required")
    destination = tmp_path / "changed"
    shutil.copytree(source, destination)
    manifest = json.loads((destination / "manifest.json").read_text())
    manifest["threshold"] = 0.9
    (destination / "manifest.json").unlink()
    (destination / "manifest.json").write_text(json.dumps(manifest))
    digest = hashlib.sha256((destination / "manifest.json").read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="threshold"):
        verify_onnx_artifact(destination, digest)
