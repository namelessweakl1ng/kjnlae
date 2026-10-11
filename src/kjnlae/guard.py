"""Reusable input screening. No scan metadata can authorize a tool."""

from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

from kjnlae.detection.inspection import inspect
from kjnlae.detection.rules import detect
from kjnlae.schemas import Classification, Decision, ScanRequest, ScanResult


class Classifier(Protocol):
    def classify(self, text: str) -> Classification: ...


@dataclass(frozen=True)
class ScanPolicy:
    id: str = "input-v1"
    warn: int = 25
    review: int = 60
    block: int = 80
    ml_threshold: float = 0.8

    def __post_init__(self) -> None:
        if not 0 <= self.warn < self.review < self.block <= 100:
            raise ValueError("Policy requires ordered thresholds")
        if not 0 <= self.ml_threshold <= 1:
            raise ValueError("Invalid ML threshold")


class Guard:
    def __init__(
        self, classifier: Classifier | None = None, policy: ScanPolicy | None = None
    ) -> None:
        self.classifier = classifier
        self.policy = policy or ScanPolicy()

    def scan(self, text: str, **context: object) -> ScanResult:
        request = ScanRequest.model_validate({"text": text, **context})
        return self.scan_request(request)

    def scan_request(self, request: ScanRequest) -> ScanResult:
        started = perf_counter()
        views, structural, complete = inspect(request.text)
        findings = structural + detect(request.text, views)
        classification = None
        if request.mode != "deterministic":
            classification = (
                self.classifier.classify(request.text)
                if self.classifier
                else Classification(status="unavailable", detail="No classifier configured")
            )
            complete = complete and classification.status == "available"
        score = max((f.severity for f in findings), default=0) if request.mode != "ml" else 0
        if (
            classification
            and classification.score is not None
            and classification.score >= self.policy.ml_threshold
        ):
            score = max(score, self.policy.block)
        # This changes screening only. Claims about analysis/trust never affect authorization.
        analytical = request.purpose in {"analysis", "code"}
        if analytical and score:
            score = min(score, self.policy.warn + 5)
        elif request.sensitive_access and score:
            score = min(100, score + 10)
        decision: Decision = (
            "BLOCK"
            if score >= self.policy.block
            else "REQUIRE_REVIEW"
            if score >= self.policy.review
            else "WARN"
            if score >= self.policy.warn
            else "ALLOW"
        )
        if not complete and decision != "BLOCK":
            decision = "REQUIRE_REVIEW"
        return ScanResult(
            decision=decision,
            risk_level=(
                "critical"
                if score >= 90
                else "high"
                if score >= 60
                else "medium"
                if score >= 25
                else "low"
            ),
            risk_score=score,
            detection_mode=request.mode,
            findings=findings,
            classification=classification,
            explanation=(
                "Inspection incomplete; do not treat this input as cleared."
                if not complete
                else "Evidence of suspicious instructions; not proof of a successful attack."
                if findings
                else "No configured detector evidence found; this does not establish safety."
            ),
            mitigation=(
                "Keep content in its original trust boundary and independently authorize actions."
                if findings or not complete
                else "Maintain least-privilege tool and output controls."
            ),
            policy_id=self.policy.id,
            latency_ms=round((perf_counter() - started) * 1000, 3),
            inspection_complete=complete,
            source=request.source,
            source_trust="user-supplied" if request.source == "user" else "untrusted",
        )
