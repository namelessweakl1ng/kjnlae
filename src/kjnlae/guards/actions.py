"""Independent authorization. Authorities and approval calls belong to trusted host code."""

import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass

from kjnlae.schemas import Action, ActionResult


def action_digest(action: Action) -> str:
    return hashlib.sha256(
        json.dumps(action.model_dump(), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class Grant:
    """Exact action issued by trusted application logic, never by an LLM/parser."""

    action: Action


@dataclass(frozen=True)
class Authority:
    principal: str
    owned_resources: frozenset[str]
    grants: tuple[Grant, ...]
    destinations: frozenset[str] = frozenset()


class ActionGateway:
    def __init__(self, approval_ttl: float = 300, max_approvals: int = 1024) -> None:
        if not 0 < approval_ttl <= 3600 or not 1 <= max_approvals <= 10000:
            raise ValueError("Invalid approval limits")
        self.approval_ttl = approval_ttl
        self.max_approvals = max_approvals
        self._approvals: dict[str, tuple[str, str, float]] = {}
        self._lock = threading.Lock()

    def _violation(self, action: Action, authority: Authority) -> str | None:
        if not authority.principal:
            return "Authenticated principal required"
        if action.resource not in authority.owned_resources:
            return "Resource ownership denied"
        if action.tool == "admin":
            return "Privileged tool is not supported"
        if not any(action_digest(g.action) == action_digest(action) for g in authority.grants):
            return "Exact action is outside trusted user intent"
        if action.tool == "send_email":
            if not action.destination or action.destination not in authority.destinations:
                return "Destination denied"
            if set(action.parameters) - {"body", "subject"}:
                return "Unknown email parameters"
        elif action.destination is not None or action.parameters:
            return "Unexpected action parameters"
        if any(len(v) > 4096 for v in action.parameters.values()):
            return "Action parameter exceeds limit"
        return None

    def approve(self, action: Action, authority: Authority) -> str:
        """Invoke only AFTER a trusted human approval ceremony. No public approval endpoint."""
        violation = self._violation(action, authority)
        if violation:
            raise ValueError(violation)
        with self._lock:
            now = time.monotonic()
            self._approvals = {k: v for k, v in self._approvals.items() if v[2] > now}
            if len(self._approvals) >= self.max_approvals:
                raise ValueError("Approval capacity reached")
            token = secrets.token_urlsafe(32)
            self._approvals[token] = (
                authority.principal,
                action_digest(action),
                now + self.approval_ttl,
            )
            return token

    def authorize(
        self,
        action: Action,
        authority: Authority,
        approval_token: str | None = None,
        *,
        controls_ready: bool = True,
    ) -> ActionResult:
        violation = self._violation(action, authority)
        if violation:
            return ActionResult(decision="BLOCK", reason=violation)
        sensitive = action.tool != "read_document"
        if not controls_ready:
            return ActionResult(
                decision="BLOCK" if sensitive else "WARN",
                reason="Required control unavailable; read-only degraded mode",
            )
        if sensitive:
            with self._lock:
                record = self._approvals.get(approval_token or "")
                valid = (
                    record is not None
                    and record[0] == authority.principal
                    and record[1] == action_digest(action)
                    and record[2] > time.monotonic()
                )
                if not valid:
                    return ActionResult(
                        decision="REQUIRE_REVIEW",
                        reason="Exact action requires fresh human approval",
                    )
                del self._approvals[approval_token or ""]
        return ActionResult(
            decision="ALLOW", reason="Principal, intent, ownership and parameters authorized"
        )
