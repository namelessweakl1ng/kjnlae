from kjnlae.integrations.hosts import run_enterprise_case, run_hospital_case


class ScanStub:
    def __init__(self, decision: str = "ALLOW") -> None:
        self.decision = decision

    def scan(self, text: str, **context: object):
        return type(
            "Scan", (), {"policy_decision": self.decision, "detection_status": "NO_EVIDENCE_FOUND"}
        )()


def test_hospital_grants_and_model_failure():
    assert run_hospital_case("own_patient", ScanStub())["action_status"] == "EXECUTED"
    assert run_hospital_case("other_patient", ScanStub())["action_status"] == "DENIED"
    assert run_hospital_case("cross_tenant", ScanStub())["action_status"] == "DENIED"
    assert run_hospital_case("injected_note", ScanStub("BLOCK"))["action_status"] == "DENIED"
    assert run_hospital_case("own_patient", ScanStub("REQUIRE_REVIEW"))["action_status"] == "DENIED"


def test_enterprise_grants_destinations_and_independent_denial():
    assert run_enterprise_case("public_policy", ScanStub())["action_status"] == "EXECUTED"
    assert run_enterprise_case("hr_authorized", ScanStub())["action_status"] == "EXECUTED"
    assert run_enterprise_case("other_employee", ScanStub())["action_status"] == "DENIED"
    assert run_enterprise_case("redirect_email", ScanStub())["action_status"] == "DENIED"
    assert run_enterprise_case("detector_miss", ScanStub())["action_status"] == "DENIED"
    assert run_enterprise_case("admin_tool", ScanStub())["action_status"] == "DENIED"
