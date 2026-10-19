"""Immediate host-owned tool execution, after independent exact authorization."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

from kjnlae.guards.actions import ActionGateway
from kjnlae.guards.resources import HostAuthority, ProposedAction, ResourceCatalog

T = TypeVar("T")


@dataclass(frozen=True)
class ExecutionResult(Generic[T]):
    """Distinguish a denied call from a callback with an uncertain outcome."""

    status: Literal["EXECUTED", "DENIED", "UNKNOWN"]
    reason: str
    value: T | None = None


class GuardedExecutor:
    """Execute only host callbacks that pass current resource authorization."""

    def __init__(self, gateway: ActionGateway, catalog: ResourceCatalog) -> None:
        self.gateway = gateway
        self.catalog = catalog

    def execute(
        self,
        action: ProposedAction,
        authority: HostAuthority,
        callback: Callable[[ProposedAction], T],
        *,
        approval_token: str | None = None,
        controls_ready: bool = True,
    ) -> ExecutionResult[T]:
        """Check grants and approval, recheck the resource, then invoke once."""
        authorization = self.gateway.authorize_v2(
            action,
            authority,
            self.catalog,
            approval_token=approval_token,
            controls_ready=controls_ready,
        )
        if authorization.decision != "ALLOW":
            return ExecutionResult("DENIED", authorization.reason)
        record = self.catalog.resolve(action.resource, action.tenant)
        if (
            record is None
            or record.version != authorization.resource_version
            or record.tenant != authorization.resource_tenant
            or record.owner != authorization.resource_owner
        ):
            return ExecutionResult("DENIED", "Resource changed before execution")
        try:
            still_current, value = self.catalog.run_if_current(record, lambda: callback(action))
        except Exception:
            # Side effects could have happened before the callback failed. Never retry here.
            return ExecutionResult("UNKNOWN", "Host callback outcome uncertain")
        if not still_current:
            return ExecutionResult("DENIED", "Resource version changed before execution")
        return ExecutionResult("EXECUTED", "Authorized host callback completed", value)
