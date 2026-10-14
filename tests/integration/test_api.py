from fastapi.testclient import TestClient

from kjnlae.api.app import create_app
from kjnlae.api.config import Settings
from kjnlae.api.middleware import MAX_REQUEST_BODY_BYTES


def test_v2_limits_and_security_headers():
    with TestClient(create_app(Settings(rate_limit=20))) as client:
        assert client.post("/v2/scan", json={"text": "x" * 32769}).status_code == 422
        oversized = client.post("/v2/scan", content=b"x" * (MAX_REQUEST_BODY_BYTES + 1))
        assert oversized.status_code == 413
        assert (
            client.post("/v2/scan", json={"text": "hello", "source": "system"}).status_code == 422
        )
        assert "unsafe-inline" not in client.get("/health/live").headers["content-security-policy"]
