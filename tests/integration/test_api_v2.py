import pytest
from fastapi.testclient import TestClient

from kjnlae.api.app import create_app
from kjnlae.api.config import Settings


def test_v2_missing_model_is_explicit_and_v1_scan_gone(tmp_path):
    with TestClient(create_app(Settings(database=str(tmp_path / "audit.db")))) as client:
        response = client.post("/v2/scan", json={"text": "Hello"})
        assert response.status_code == 200
        assert response.json()["detection_status"] == "INCOMPLETE"
        assert response.json()["model_status"] == "MISSING"
        assert response.json()["policy_decision"] != "ALLOW"
        assert client.post("/v1/scan", json={"text": "Hello"}).status_code == 410
        assert client.get("/health/ready").status_code == 503
        assert (
            client.get("/v2/system/capabilities").json()["detector"]
            == "fine_tuned_local_transformer_only"
        )


def test_v2_rejects_mode_and_forged_authority(tmp_path):
    with TestClient(create_app(Settings(database=str(tmp_path / "audit.db")))) as client:
        for payload in (
            {"text": "hello", "mode": "deterministic"},
            {"text": "hello", "principal": "admin"},
        ):
            assert client.post("/v2/scan", json=payload).status_code == 422
        assert (
            client.post(
                "/v2/guard/action",
                json={"tool": "admin", "tenant": "demo", "resource": "x", "approved": True},
            ).status_code
            == 422
        )


def test_v2_production_auth(tmp_path):
    with pytest.raises(ValueError):
        Settings(production=True)
    settings = Settings(
        database=str(tmp_path / "audit.db"),
        production=True,
        api_key="x" * 32,
        model_dir=str(tmp_path / "missing"),
        model_hash="a" * 64,
    )
    with TestClient(create_app(settings)) as client:
        assert client.post("/v2/scan", json={"text": "Hello"}).status_code == 401
        assert (
            client.post(
                "/v2/scan", json={"text": "Hello"}, headers={"Authorization": "Bearer " + "x" * 32}
            ).status_code
            == 200
        )
        assert (
            client.get("/v2/lab", headers={"Authorization": "Bearer " + "x" * 32}).status_code
            == 404
        )
