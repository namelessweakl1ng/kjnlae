"""Independent authorization. Authorities and approval calls belong to trusted host code."""

import hashlib
import secrets
import threading
import time

from kjnlae.guards.resources import HostAuthority, ProposedAction, ResourceCatalog
from kjnlae.schemas_v2 import AuthorizationResultV2


class ActionGateway:
    """Authorize proposed actions independently of prompt-injection scores."""

    def __init__(self, approval_ttl: float = 300, max_approvals: int = 1024) -> None:
        if not 0 < approval_ttl <= 3600 or not 1 <= max_approvals <= 10000:
            raise ValueError("Invalid approval limits")
        self.approval_ttl = approval_ttl
        self.max_approvals = max_approvals
        self._approvals_v2: dict[str, tuple[str, str, str, int, float]] = {}
        self._lock = threading.Lock()

    def approve_v2(
        self,
        action: ProposedAction,
        authority: HostAuthority,
        catalog: ResourceCatalog,
        *,
        reviewer: str,
    ) -> str:
        """Trusted host calls this only after authenticating a human reviewer."""
        if not reviewer or reviewer == authority.principal:
            raise ValueError("Distinct authenticated reviewer required")
        decision = self.authorize_v2(action, authority, catalog)
        if decision.decision != "REQUIRE_REVIEW":
            raise ValueError("Action is not eligible for human approval")
        record = catalog.resolve(action.resource)
        assert record is not None
        with self._lock:
            now = time.monotonic()
            self._approvals_v2 = {
                token: approval
                for token, approval in self._approvals_v2.items()
                if approval[4] > now
            }
            if len(self._approvals_v2) >= self.max_approvals:
                raise ValueError("Approval capacity reached")
            token = secrets.token_urlsafe(32)
            self._approvals_v2[token] = (
                decision.action_digest,
                authority.principal,
                authority.tenant,
                record.version,
                now + self.approval_ttl,
            )
            return token

    def authorize_v2(
        self,
        action: ProposedAction,
        authority: HostAuthority,
        catalog: ResourceCatalog,
        *,
        approval_token: str | None = None,
        controls_ready: bool = True,
    ) -> AuthorizationResultV2:
        """Check exact host-owned identity, grants, resource state and approval.

        This only returns a decision. The trusted executor consumes an approval
        while performing the approved callback, never during an HTTP preview.
        """
        digest = hashlib.sha256(action.model_dump_json().encode()).hexdigest()

        def deny(reason: str) -> AuthorizationResultV2:
            return AuthorizationResultV2(decision="BLOCK", reason=reason, action_digest=digest)

        if not authority.principal or action.tenant != authority.tenant:
            return deny("Verified principal and tenant required")
        if action.tool == "admin" or action.tool not in authority.allowed_tools:
            return deny("Tool is not registered for this principal")
        record = catalog.resolve(action.resource)
        if record is None or record.tenant != authority.tenant:
            return deny("Resource or tenant denied")
        if not any(
            grant.permits(action, authority.principal, record.version) for grant in authority.grants
        ):
            return deny("Current exact resource grant required")
        if action.tool == "read_document":
            if action.destination is not None or action.parameters:
                return deny("Read action cannot carry export parameters")
        elif action.tool == "send_email":
            if not action.destination or action.destination not in authority.destinations:
                return deny("Destination denied")
            if set(action.parameters) - {"subject", "body"}:
                return deny("Unexpected email parameters")
        elif action.destination is not None or action.parameters:
            return deny("Unexpected parameters")
        if any(len(value) > 4096 for value in action.parameters.values()):
            return deny("Action parameter exceeds limit")
        if not controls_ready:
            return AuthorizationResultV2(
                decision="BLOCK" if record.sensitive or action.tool != "read_document" else "WARN",
                reason="Required control unavailable",
                action_digest=digest,
            )
        if action.tool != "read_document":
            with self._lock:
                approval = self._approvals_v2.get(approval_token or "")
                if (
                    approval is not None
                    and approval[0] == digest
                    and approval[1] == authority.principal
                    and approval[2] == authority.tenant
                    and approval[3] == record.version
                    and approval[4] > time.monotonic()
                ):
                    del self._approvals_v2[approval_token or ""]
                    return AuthorizationResultV2(
                        decision="ALLOW",
                        reason="Exact one-use approval consumed",
                        action_digest=digest,
                        resource_version=record.version,
                        resource_tenant=record.tenant,
                        resource_owner=record.owner,
                    )
            return AuthorizationResultV2(
                decision="REQUIRE_REVIEW",
                reason="Exact human approval required",
                action_digest=digest,
            )
        return AuthorizationResultV2(
            decision="ALLOW",
            reason="Trusted identity, tenant, resource and grant verified",
            action_digest=digest,
            resource_version=record.version,
            resource_tenant=record.tenant,
            resource_owner=record.owner,
        )
