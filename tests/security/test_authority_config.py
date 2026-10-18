import json
import os

from fastapi.testclient import TestClient

from kjnlae.api.app import create_app
from kjnlae.api.config import Settings


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
        ),
        encoding="utf-8",
        newline="\n",
    )
    os.chmod(authority, 0o600)
    settings = Settings(
        authority_v2_path=str(authority),
        model_dir=str(tmp_path / "missing"),
        model_hash="a" * 64,
    )
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
