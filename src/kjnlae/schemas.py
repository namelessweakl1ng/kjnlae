"""Strict public data contracts. Context supplied to scanning grants no authority."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Decision = Literal["ALLOW", "WARN", "BLOCK", "REQUIRE_REVIEW"]
Source = Literal[
    "user", "retrieved_document", "webpage", "email", "attachment", "tool_response", "agent"
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


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

    @model_validator(mode="after")
    def bounded_output(self) -> "OutputRequest":
        if len(self.text) + sum(len(v) for v in (self.structured or {}).values()) > 32768:
            raise ValueError("Combined output exceeds 32768 characters")
        return self


class OutputResult(StrictModel):
    decision: Decision
    violations: list[str]
    policy_id: str = "output-v1"
