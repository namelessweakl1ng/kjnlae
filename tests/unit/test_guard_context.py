from kjnlae import Guard


def test_guard_context_manager_closes_owned_classifier():
    with Guard() as guard:
        assert guard.scan("A harmless sentence.").detection_status == "INCOMPLETE"


def test_default_model_path_is_reported_when_not_installed(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("KJNLAE_MODEL_DIR", raising=False)
    monkeypatch.delenv("KJNLAE_MODEL_HASH", raising=False)
    with Guard() as guard:
        assert guard.capabilities()["model_status"] == "MISSING"
