"""Trusted host context is never parsed from the scan request body."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TrustedSecurityContext:
    """Host-verified identity and task context for policy, never scan JSON."""

    principal: str
    tenant: str
    task: str
    analysis_intent: bool = False
    sensitive: bool = False

    def __post_init__(self) -> None:
        if not self.principal or not self.tenant:
            raise ValueError("Verified principal and tenant are required")
