"""Model-only inspection contracts. Request JSON conveys content, never authority."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kjnlae.schemas import Decision, Source

DetectionStatus = Literal["NO_EVIDENCE_FOUND", "MALICIOUS_INDICATORS", "INCOMPLETE"]
ModelStatus = Literal["AVAILABLE", "MISSING", "UNAVAILABLE", "CORRUPTED", "TIMED_OUT", "ERROR"]


class StrictV2(BaseModel):
    """Immutable v2 contract that rejects unexpected request fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ContentEnvelope(StrictV2):
    """Untrusted content with origin metadata, not an authority claim."""

    text: str = Field(min_length=1, max_length=32768)
    source: Source = "user"
    origin_id: str | None = Field(default=None, max_length=256)


class InspectionRequestV2(StrictV2):
    """Bounded model-scan request; context_ref conveys no permissions."""

    text: str = Field(min_length=1, max_length=32768)
    source: Source = "user"
    context_ref: str | None = Field(default=None, max_length=128)


class WindowEvidence(StrictV2):
    """A scored inspection window with offsets in the original text."""

    view: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    score: float = Field(ge=0, le=1)
    model_hash: str


class InspectionResultV2(StrictV2):
    """Model result and input-policy decision, separate from tool approval."""

    detection_status: DetectionStatus
    policy_decision: Decision
    model_status: ModelStatus
    evidence: tuple[WindowEvidence, ...] = ()
    windows: tuple[WindowEvidence, ...] = ()
    threshold: float | None = Field(default=None, ge=0, le=1)
    coverage: dict[str, int] = Field(default_factory=dict)
    reason_codes: tuple[str, ...] = ()
    policy_id: str = "model-only-v2"
    latency_ms: float = Field(default=0, ge=0)
    inspection_complete: bool
    model_hash: str | None = None
    model_score: float | None = Field(default=None, ge=0, le=1)
    risk_level: Literal["unknown", "low", "elevated", "high"] = "unknown"
    explanation: str = ""
    recommended_action: str = ""

    @model_validator(mode="after")
    def incomplete_is_not_clear(self) -> "InspectionResultV2":
        """Prevent partial or failed inspection from becoming a clear result."""
        if self.detection_status == "INCOMPLETE" and self.policy_decision in {"ALLOW", "WARN"}:
            raise ValueError("Incomplete inspection requires review or block")
        if not self.inspection_complete and self.detection_status != "INCOMPLETE":
            raise ValueError("Partial inspection must report INCOMPLETE")
        return self


class AuthorizationResultV2(StrictV2):
    """Decision about one proposed action; executed is false for HTTP preview."""

    decision: Decision
    reason: str
    action_digest: str
    executed: bool = False
    policy_id: str = "action-v2"
    resource_version: int | None = None
    resource_tenant: str | None = None
    resource_owner: str | None = None
