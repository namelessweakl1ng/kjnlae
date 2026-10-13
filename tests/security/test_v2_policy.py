from kjnlae.classifiers.local import LocalInference
from kjnlae.context import TrustedSecurityContext
from kjnlae.policies.decision import InputPolicy


def test_missing_model_requires_review_or_blocks_sensitive() -> None:
    policy = InputPolicy()
    missing = LocalInference("MISSING", False, reason="MODEL_MISSING")
    assert (
        policy.decide(missing, True, "retrieved_document", None, 0.6).decision == "REQUIRE_REVIEW"
    )
    sensitive = TrustedSecurityContext("clinician", "hospital", "Read patient", sensitive=True)
    assert policy.decide(missing, True, "retrieved_document", sensitive, 0.6).decision == "BLOCK"


def test_model_score_alone_assigns_injection_status() -> None:
    policy = InputPolicy()
    context = TrustedSecurityContext("user", "tenant", "employee lookup")
    assert (
        policy.decide(
            LocalInference("AVAILABLE", True, score=0.1), True, "user", context, 0.6
        ).detection_status
        == "NO_EVIDENCE_FOUND"
    )
    positive = policy.decide(
        LocalInference("AVAILABLE", True, score=0.9), True, "retrieved_document", context, 0.6
    )
    assert positive.detection_status == "MALICIOUS_INDICATORS"
    assert positive.decision == "BLOCK"


def test_partial_coverage_overrides_negative_score() -> None:
    outcome = InputPolicy().decide(
        LocalInference("AVAILABLE", True, score=0.0), False, "webpage", None, 0.6
    )
    assert outcome.detection_status == "INCOMPLETE"
    assert outcome.decision == "REQUIRE_REVIEW"
