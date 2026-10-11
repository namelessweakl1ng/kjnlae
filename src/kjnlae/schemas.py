"""Strict public data contracts. Context supplied to scanning grants no authority."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Decision = Literal["ALLOW", "WARN", "BLOCK", "REQUIRE_REVIEW"]
Source = Literal[
    "user", "retrieved_document", "webpage", "email", "attachment", "tool_response", "agent"
]
Mode = Literal["deterministic", "ml", "combined"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScanRequest(StrictModel):
    text: str = Field(min_length=1, max_length=32768)
    source: Source = "user"
    purpose: Literal["instruction", "reference", "analysis", "code"] = "reference"
    task: str = Field(default="", max_length=2048)
    requested_action: str = Field(default="", max_length=256)
    sensitive_access: bool = False
    destination: str | None = Field(default=None, max_length=512)
    mode: Mode = "deterministic"


class Finding(StrictModel):
    rule_id: str
    category: str
    explanation: str
    severity: int = Field(ge=0, le=100)
    start: int
    end: int
    evidence: str
    view: str = "original"


class Classification(StrictModel):
    status: Literal["available", "unavailable", "timeout", "error", "coverage_exceeded"]
    score: float | None = None
    model_id: str | None = None
    revision: str | None = None
    windows: int = 0
    detail: str = ""


class ScanResult(StrictModel):
    decision: Decision
    risk_level: Literal["low", "medium", "high", "critical"]
    risk_score: int
    detection_mode: Mode
    findings: list[Finding]
    classification: Classification | None = None
    explanation: str
    mitigation: str
    policy_id: str
    latency_ms: float
    inspection_complete: bool
    source: Source
    source_trust: Literal["untrusted", "user-supplied"]


class Action(StrictModel):
    tool: Literal["read_document", "send_email", "delete_document", "admin"]
    resource: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    destination: str | None = Field(default=None, max_length=254)
    parameters: dict[str, str] = Field(default_factory=dict, max_length=8)


class ActionRequest(StrictModel):
    action: Action
    approval_token: str | None = Field(default=None, max_length=128)


class ActionResult(StrictModel):
    decision: Decision
    reason: str
    policy_id: str = "action-v1"
    executed: bool = False


class OutputRequest(StrictModel):
    text: str = Field(max_length=32768)
    structured: dict[str, str] | None = Field(default=None, max_length=16)


class OutputResult(StrictModel):
    decision: Decision
    violations: list[str]
    policy_id: str = "output-v1"
