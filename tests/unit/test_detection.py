"""Model-only scan contract regressions; category quality is measured in evaluation."""

import base64

import pytest
from pydantic import ValidationError

from kjnlae import Guard
from kjnlae.schemas_v2 import InspectionRequestV2


def test_oversize_rejected() -> None:
    with pytest.raises(ValidationError):
        Guard().scan("a" * 32769)


def test_encoded_view_budget_is_explicitly_incomplete() -> None:
    tokens = [base64.b64encode(f"ordinary text number {i:04}".encode()).decode() for i in range(17)]
    result = Guard().scan(" ".join(tokens), source="retrieved_document")
    assert not result.inspection_complete
    assert result.detection_status == "INCOMPLETE"
    assert result.policy_decision == "REQUIRE_REVIEW"


def test_retired_mode_and_caller_purpose_are_rejected() -> None:
    for field, value in (("mode", "combined"), ("purpose", "analysis")):
        with pytest.raises(ValidationError):
            InspectionRequestV2.model_validate({"text": "hello", field: value})
