"""Strict public data contracts. Context supplied to scanning grants no authority."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

Decision = Literal["ALLOW", "WARN", "BLOCK", "REQUIRE_REVIEW"]
Source = Literal[
    "user", "retrieved_document", "webpage", "email", "attachment", "tool_response", "agent"
]


class StrictModel(BaseModel):
    """Reject unknown fields so text cannot smuggle undeclared authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class OutputInspection(StrictModel):
    """Content-only output decision; use OutputGuard.release for resource data."""

    decision: Decision
    violations: list[str]
    policy_id: str = "output-v2"
