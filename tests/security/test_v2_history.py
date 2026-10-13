import json
import os

from fastapi.testclient import TestClient

from kjnlae.api.app import create_app
from kjnlae.api.config import Settings
from kjnlae.storage.sqlite import SQLiteHistory


def test_tenant_history_filters_and_never_stores_prompts(tmp_path):
    database = str(tmp_path / "audit.db")
    store = SQLiteHistory(database)
    store.record(
        {"policy_decision": "BLOCK", "model_status": "AVAILABLE", "text": "PRIVATE PATIENT SECRET"},
        tenant="hospital-a",
    )
    store.record({"policy_decision": "ALLOW", "model_status": "AVAILABLE"}, tenant="hospital-b")
    assert len(store.list(tenant="hospital-a")) == 1
    assert len(store.list(tenant="hospital-b")) == 1
    assert "PRIVATE PATIENT SECRET" not in json.dumps(store.list(tenant="hospital-a"))
    store.clear(tenant="hospital-a")
    assert len(store.list(tenant="hospital-b")) == 1


def test_host_authority_file_is_server_owned_and_denies_forgery(tmp_path):
    authority = tmp_path / "authority.json"
    authority.write_text(
        json.dumps(
            {
                "principal": "alice",
                "tenant": "tenant-a",
                "task": "read handbook",
                "allowed_tools": ["read_document"],
                "destinations": [],
                "resources": [
                    {
                        "id": "handbook",
                        "tenant": "tenant-a",
                        "owner": "company",
                        "version": 1,
                        "sensitive": False,
                    }
                ],
                "grants": [{"resource": "handbook", "operation": "read_document", "version": 1}],
            }
        )
    )
    os.chmod(authority, 0o600)
    settings = Settings(database=str(tmp_path / "audit.db"), authority_v2_path=str(authority))
    with TestClient(create_app(settings)) as client:
        allowed = client.post(
            "/v2/guard/action",
            json={
                "action": {"tool": "read_document", "tenant": "tenant-a", "resource": "handbook"}
            },
        )
        assert allowed.json()["decision"] != "ALLOW"  # model control unavailable
        forged = client.post(
            "/v2/guard/action",
            json={
                "action": {"tool": "read_document", "tenant": "tenant-b", "resource": "handbook"}
            },
        )
        assert forged.json()["decision"] == "BLOCK"
