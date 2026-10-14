from fastapi.testclient import TestClient

from kjnlae.api.app import create_app
from kjnlae.api.config import Settings


def test_v1_http_routes_are_absent() -> None:
    with TestClient(create_app(Settings())) as client:
        for path in ("/v1/scan", "/v1/guard/input", "/v1/guard/action", "/v1/guard/output"):
            response = client.post(path, json={})
            assert response.status_code == 404, path
        assert not any(route.path.startswith("/v1/") for route in client.app.routes)


def test_v2_action_still_rejects_untrusted_authority() -> None:
    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/v2/guard/action",
            json={
                "action": {"tool": "admin", "tenant": "local", "resource": "x"},
                "approved": True,
            },
        )
        assert response.status_code == 422
