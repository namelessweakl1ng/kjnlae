import time

from fastapi.testclient import TestClient

from kjnlae.api.chatbot import create_chatbot_app
from kjnlae.guard import Guard
from kjnlae.guards.resources import HostAuthority, ResourceCatalog, ResourceGrant, ResourceRecord


class ScanStub:
    def __init__(self, decision="ALLOW"):
        self.decision = decision
        self.seen = []

    def scan(self, text, **context):
        from types import SimpleNamespace

        self.seen.append(text)
        return SimpleNamespace(
            policy_decision=self.decision,
            detection_status="INCOMPLETE" if self.decision != "ALLOW" else "NO_EVIDENCE_FOUND",
        )


def _app(scanner):
    catalog = ResourceCatalog(
        (
            ResourceRecord("patient-1", "hospital", "ward", 1),
            ResourceRecord("patient-2", "hospital", "ward", 1),
            ResourceRecord("hr-1", "enterprise", "hr", 1),
        )
    )
    identities = {
        "hospital-key-with-at-least-32-chars": HostAuthority(
            "doctor",
            "hospital",
            "Summarize assigned patient",
            frozenset({"read_document"}),
            (
                ResourceGrant(
                    "doctor", "hospital", "patient-1", "read_document", 1, time.time() + 300
                ),
            ),
        ),
        "enterprise-key-with-at-least-32-chars": HostAuthority(
            "analyst",
            "enterprise",
            "Summarize permitted company data",
            frozenset({"read_document"}),
            (
                ResourceGrant(
                    "analyst", "enterprise", "hr-1", "read_document", 1, time.time() + 300
                ),
            ),
        ),
    }
    return create_chatbot_app(
        scanner,
        identities,
        catalog,
        {
            "patient-1": "Patient has a routine appointment. Follow-up labs are scheduled Friday.",
            "patient-2": "PRIVATE OTHER PATIENT",
            "hr-1": "Employee handbook summary.",
        },
    )


def test_chatbot_verified_identity_and_tenant_boundaries():
    with TestClient(_app(ScanStub())) as client:
        assert (
            client.post("/chat", json={"message": "Summarize", "resource": "patient-1"}).status_code
            == 401
        )
        headers = {"Authorization": "Bearer hospital-key-with-at-least-32-chars"}
        own = client.post(
            "/chat", headers=headers, json={"message": "Summarize", "resource": "patient-1"}
        )
        assert own.json()["action_status"] == "EXECUTED"
        assert "routine appointment" in own.json()["answer"]
        labs = client.post(
            "/chat",
            headers=headers,
            json={"message": "When are follow-up labs?", "resource": "patient-1"},
        )
        assert "scheduled Friday" in labs.json()["answer"]
        assert "routine appointment" not in labs.json()["answer"]
        for resource in ("patient-2", "hr-1"):
            denial = client.post(
                "/chat", headers=headers, json={"message": "Summarize", "resource": resource}
            )
            assert denial.json()["action_status"] == "DENIED"
            assert denial.json()["answer"] is None
            assert denial.json()["detection_decision"] == "NOT_EVALUATED"
        assert (
            client.post(
                "/chat",
                headers=headers,
                json={"message": "Summarize", "resource": "patient-1", "principal": "admin"},
            ).status_code
            == 422
        )


def test_chatbot_model_failure_and_injection_block():
    headers = {"Authorization": "Bearer hospital-key-with-at-least-32-chars"}
    for decision in ("BLOCK", "REQUIRE_REVIEW"):
        with TestClient(_app(ScanStub(decision))) as client:
            response = client.post(
                "/chat", headers=headers, json={"message": "Summarize", "resource": "patient-1"}
            )
            assert response.json()["action_status"] == "DENIED"
            assert response.json()["answer"] is None

    with TestClient(_app(Guard(model_dir="", model_hash=""))) as client:
        response = client.post(
            "/chat", headers=headers, json={"message": "Summarize", "resource": "patient-1"}
        )
        assert response.json()["action_status"] == "DENIED"
        assert response.json()["detection_decision"] == "REQUIRE_REVIEW"


def test_chatbot_uses_tenant_scoped_documents_for_shared_resource_ids():
    resource = "summary"
    catalog = ResourceCatalog(
        (
            ResourceRecord(resource, "hospital", "ward", 1),
            ResourceRecord(resource, "enterprise", "hr", 1),
        )
    )
    identities = {
        f"{'h' * 32}": HostAuthority(
            "doctor",
            "hospital",
            "Read assigned summary",
            frozenset({"read_document"}),
            (ResourceGrant("doctor", "hospital", resource, "read_document", 1, time.time() + 300),),
        ),
        f"{'e' * 32}": HostAuthority(
            "analyst",
            "enterprise",
            "Read assigned summary",
            frozenset({"read_document"}),
            (
                ResourceGrant(
                    "analyst", "enterprise", resource, "read_document", 1, time.time() + 300
                ),
            ),
        ),
    }
    app = create_chatbot_app(
        scanner := ScanStub(),
        identities,
        catalog,
        {
            ("hospital", resource): "Hospital appointment Friday.",
            ("enterprise", resource): "Enterprise handbook Monday.",
        },
    )
    with TestClient(app) as client:
        for key, expected, forbidden in (
            ("h" * 32, "Hospital appointment", "Enterprise handbook"),
            ("e" * 32, "Enterprise handbook", "Hospital appointment"),
        ):
            reply = client.post(
                "/chat",
                headers={"Authorization": f"Bearer {key}"},
                json={"message": "Summarize", "resource": resource},
            ).json()
            assert reply["action_status"] == "EXECUTED"
            assert expected in reply["answer"]
            assert forbidden not in reply["answer"]
        assert len(scanner.seen) == 2
        assert set(scanner.seen) == {"Hospital appointment Friday.", "Enterprise handbook Monday."}
        before = len(scanner.seen)
        denied = client.post(
            "/chat",
            headers={"Authorization": f"Bearer {'h' * 32}"},
            json={"message": "Summarize", "resource": "unknown"},
        ).json()
        assert denied["action_status"] == "DENIED"
        assert denied["answer"] is None
        assert denied["detection_decision"] == "NOT_EVALUATED"
        assert len(scanner.seen) == before
