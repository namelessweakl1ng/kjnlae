"""Apply model evidence and fail-closed policy without lexical attack rules."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from kjnlae.classifiers.local import LocalInference
from kjnlae.context import TrustedSecurityContext
from kjnlae.schemas import Decision, Source
from kjnlae.schemas_v2 import DetectionStatus

Profile = Literal["general", "rag", "healthcare", "enterprise", "high_security"]


@dataclass(frozen=True)
class PolicyOutcome:
    decision: Decision
    detection_status: DetectionStatus
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class InputPolicy:
    profile: Profile = "general"
    version: str = "v2-1"
    policy_hash: str = "built-in"

    @classmethod
    def load(cls, path: Path) -> "InputPolicy":
        raw_bytes = path.read_bytes()
        data = json.loads(raw_bytes)
        if set(data) != {"profile", "version"} or data["profile"] not in {
            "general",
            "rag",
            "healthcare",
            "enterprise",
            "high_security",
        }:
            raise ValueError("Unsupported or mutable policy configuration")
        if not isinstance(data["version"], str) or not data["version"]:
            raise ValueError("Policy version required")
        return cls(data["profile"], data["version"], hashlib.sha256(raw_bytes).hexdigest())

    @property
    def id(self) -> str:
        return f"{self.profile}-{self.version}-{self.policy_hash[:12]}"

    def decide(
        self,
        inference: LocalInference,
        preprocessing_complete: bool,
        source: Source,
        trusted_context: TrustedSecurityContext | None,
        threshold: float,
    ) -> PolicyOutcome:
        if not 0 < threshold <= 1:
            raise ValueError("Calibrated model threshold is required")
        sensitive = self.profile in {"healthcare", "enterprise", "high_security"} or (
            trusted_context is not None and trusted_context.sensitive
        )
        if (
            inference.status != "AVAILABLE"
            or not inference.inspection_complete
            or (not preprocessing_complete)
        ):
            reason = inference.reason or "COVERAGE_EXCEEDED"
            return PolicyOutcome(
                "BLOCK" if sensitive else "REQUIRE_REVIEW", "INCOMPLETE", (reason,)
            )
        if inference.score is None:
            return PolicyOutcome(
                "BLOCK" if sensitive else "REQUIRE_REVIEW", "INCOMPLETE", ("MODEL_NO_SCORE",)
            )
        if inference.score < threshold:
            return PolicyOutcome("ALLOW", "NO_EVIDENCE_FOUND", ("MODEL_BELOW_THRESHOLD",))
        if trusted_context is not None and trusted_context.analysis_intent:
            return PolicyOutcome("WARN", "MALICIOUS_INDICATORS", ("TRUSTED_ANALYSIS",))
        return PolicyOutcome(
            "REQUIRE_REVIEW" if source == "user" and not sensitive else "BLOCK",
            "MALICIOUS_INDICATORS",
            ("MODEL_AT_OR_ABOVE_THRESHOLD",),
        )
