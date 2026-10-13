import pytest
from pydantic import ValidationError

from kjnlae.schemas_v2 import InspectionRequestV2, InspectionResultV2


def test_scan_request_rejects_mode_and_identity_claims() -> None:
    for key, value in (("mode", "deterministic"), ("principal", "admin"), ("approved", True)):
        with pytest.raises(ValidationError):
            InspectionRequestV2.model_validate({"text": "hello", key: value})


def test_incomplete_result_cannot_claim_allow() -> None:
    with pytest.raises(ValidationError):
        InspectionResultV2(
            detection_status="INCOMPLETE",
            policy_decision="ALLOW",
            model_status="MISSING",
            inspection_complete=False,
        )
