import hashlib

from kjnlae import Guard
from kjnlae.classifiers.artifacts import ArtifactManifest
from kjnlae.classifiers.local import LocalClassifier


def test_guard_context_manager_closes_owned_classifier(monkeypatch, tmp_path):
    # Artifact verification is mocked here; an actual owned classifier still
    # exercises Guard's context-manager cleanup without loading model weights.
    artifact = ArtifactManifest(tmp_path, "a" * 64, "test", "base", 1, 0.5, "EXPERIMENTAL")
    closed = []
    monkeypatch.setattr("kjnlae.guard.verify_onnx_artifact", lambda *_: artifact)
    monkeypatch.setattr(LocalClassifier, "close", lambda self: closed.append(self))
    with Guard(model_dir=str(tmp_path), model_hash="a" * 64) as guard:
        assert isinstance(guard.classifier, LocalClassifier)
    assert closed == [guard.classifier]


def test_malformed_manifest_is_reported_as_corrupted(tmp_path):
    (tmp_path / "manifest.json").write_text("[]")
    digest = hashlib.sha256((tmp_path / "manifest.json").read_bytes()).hexdigest()
    with Guard(model_dir=str(tmp_path), model_hash=digest) as guard:
        result = guard.scan("A harmless sentence.")
        assert result.detection_status == "INCOMPLETE"
        assert guard.capabilities()["model_status"] == "CORRUPTED"


def test_default_model_path_is_reported_when_not_installed(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr("kjnlae.classifiers.artifacts.Path.home", lambda: tmp_path)
    monkeypatch.delenv("KJNLAE_MODEL_DIR", raising=False)
    monkeypatch.delenv("KJNLAE_MODEL_HASH", raising=False)
    with Guard() as guard:
        assert guard.capabilities()["model_status"] == "MISSING"
