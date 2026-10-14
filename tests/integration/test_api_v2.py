import time

import pytest
from fastapi.testclient import TestClient

from kjnlae.api.app import create_app
from kjnlae.api.config import Settings
from kjnlae.guards.actions import ActionGateway
from kjnlae.guards.executor import GuardedExecutor
from kjnlae.guards.resources import (
    HostAuthority,
    ProposedAction,
    ResourceCatalog,
    ResourceGrant,
    ResourceRecord,
)


def test_v2_missing_model_is_explicit_and_v1_scan_gone(tmp_path):
    settings = Settings(model_dir=str(tmp_path / "missing"), model_hash="a" * 64)
    with TestClient(create_app(settings)) as client:
        response = client.post("/v2/scan", json={"text": "Hello"})
        assert response.status_code == 200
        assert response.json()["detection_status"] == "INCOMPLETE"
        assert response.json()["model_status"] == "MISSING"
        assert response.json()["policy_decision"] != "ALLOW"
        assert client.post("/v1/scan", json={"text": "Hello"}).status_code == 404
        assert client.get("/health/ready").status_code == 503
        assert (
            client.get("/v2/system/capabilities").json()["detector"]
            == "fine_tuned_local_transformer_only"
        )
        rag = client.post(
            "/v2/rag/inspect",
            json={
                "chunks": [
                    {"text": "Retrieved passage", "source": "retrieved_document", "origin_id": "c1"}
                ]
            },
        )
        assert rag.status_code == 200
        assert rag.json()[0]["detection_status"] == "INCOMPLETE"


def test_v2_rejects_mode_and_forged_authority(tmp_path):
    with TestClient(create_app(Settings())) as client:
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
        assert (
            client.post(
                "/v2/guard/output",
                json={"text": "x" * 20000, "structured": {"summary": "x" * 20000}},
            ).status_code
            == 422
        )
        assert (
            client.post("/v2/guard/output", json={"text": "Sensitive", "resources": []}).status_code
            == 422
        )
        assert (
            client.post(
                "/v2/guard/action",
                json={
                    "action": {"tool": "send_email", "tenant": "local", "resource": "r"},
                    "approval_token": "forged",
                },
            ).status_code
            == 422
        )
        result = client.post("/v2/guard/output", json={"text": "Ordinary output"})
        assert result.status_code == 200
        assert result.json()["release_authorized"] is False


def test_v2_production_auth(tmp_path):
    with pytest.raises(ValueError):
        Settings(production=True)
    settings = Settings(
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


def test_http_preview_cannot_consume_valid_host_approval(tmp_path):
    action = ProposedAction(
        tool="send_email", tenant="company", resource="report", destination="allowed.test"
    )
    catalog = ResourceCatalog((ResourceRecord("report", "company", "alice", 1),))
    authority = HostAuthority(
        "alice",
        "company",
        "Send report",
        frozenset({"send_email"}),
        (
            ResourceGrant(
                "alice",
                "company",
                "report",
                "send_email",
                1,
                time.time() + 300,
                frozenset({"allowed.test"}),
            ),
        ),
        frozenset({"allowed.test"}),
    )
    gateway = ActionGateway()
    token = gateway.approve_v2(action, authority, catalog, reviewer="reviewer")
    app = create_app(
        Settings(),
        action_gateway=gateway,
        trusted_authority_v2=authority,
        resource_catalog=catalog,
    )
    with TestClient(app) as client:
        rejected = client.post(
            "/v2/guard/action", json={"action": action.model_dump(), "approval_token": token}
        )
        assert rejected.status_code == 422
    executed = GuardedExecutor(gateway, catalog).execute(
        action, authority, lambda _: "sent", approval_token=token
    )
    assert executed.status == "EXECUTED"
