from kjnlae import Guard


def test_guard_context_manager_closes_owned_classifier(tmp_path):
    with Guard(model_dir=str(tmp_path / "missing"), model_hash="a" * 64) as guard:
        assert guard.scan("A harmless sentence.").detection_status == "INCOMPLETE"


def test_default_model_path_is_reported_when_not_installed(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr("kjnlae.classifiers.artifacts.Path.home", lambda: tmp_path)
    monkeypatch.delenv("KJNLAE_MODEL_DIR", raising=False)
    monkeypatch.delenv("KJNLAE_MODEL_HASH", raising=False)
    with Guard() as guard:
        assert guard.capabilities()["model_status"] == "MISSING"
