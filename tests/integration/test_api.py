from fastapi.testclient import TestClient

from kjnlae.api.app import create_app
from kjnlae.api.config import Settings


def test_legacy_scan_gone_but_action_still_rejects_forgery(tmp_path):
    with TestClient(create_app(Settings(database=str(tmp_path / "a.db")))) as client:
        assert client.post("/v1/scan", json={"text": "hello"}).status_code == 410
        assert client.post("/v1/guard/input", json={"text": "hello"}).status_code == 410
        assert (
            client.post(
                "/v1/guard/action",
                json={"action": {"tool": "admin", "resource": "x"}, "approved": True},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/v1/guard/action", json={"action": {"tool": "admin", "resource": "x"}}
            ).json()["decision"]
            == "BLOCK"
        )


def test_v2_limits_privacy_and_lab(tmp_path):
    with TestClient(create_app(Settings(database=str(tmp_path / "a.db"), rate_limit=20))) as client:
        assert client.post("/v2/scan", json={"text": "x" * 32769}).status_code == 422
        assert client.post("/v2/scan", content=b"x" * 131073).status_code == 413
        assert (
            client.post("/v2/scan", json={"text": "hello", "source": "system"}).status_code == 422
        )
        client.post("/v2/scan", json={"text": "private secret"})
        assert "private secret" not in str(client.get("/v2/history").json())
        assert len(client.get("/v2/lab").json()) == 6
        assert client.get("/v2/evaluation").json()["detector"]["status"] == "INCOMPLETE"
        assert "unsafe-inline" not in client.get("/health/live").headers["content-security-policy"]
