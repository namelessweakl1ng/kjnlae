"""Small host-owned HTTP chatbot adapter with server-verified identity and resources.

The supplied document map is synthetic host data. Production hosts should provide
their own authenticated resolver, catalog and transactional tool adapter.
"""

import hmac
import re
from collections.abc import Mapping
from typing import Any, Protocol

from fastapi import FastAPI, Header, HTTPException
from pydantic import Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from kjnlae.api.middleware import LimitsMiddleware
from kjnlae.guards.actions import ActionGateway
from kjnlae.guards.executor import GuardedExecutor
from kjnlae.guards.output import OutputGuard
from kjnlae.guards.resources import HostAuthority, ProposedAction, ResourceCatalog
from kjnlae.schemas_v2 import StrictV2


class Scanner(Protocol):
    """Model scanner supplied by the host application."""

    def scan(self, text: str, **context: object) -> Any: ...


class ChatRequest(StrictV2):
    """Untrusted message and requested resource identifier."""

    message: str = Field(min_length=1, max_length=4096)
    resource: str = Field(min_length=1, max_length=128)


class ChatResult(StrictV2):
    """Expose scan, action and output decisions separately to callers."""

    detection_decision: str
    action_status: str
    output_decision: str
    answer: str | None = None


def _excerpt_for(message: str, document: str) -> str:
    """Select a grounded sentence; this is answer routing, never injection detection."""
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", document) if part.strip()]
    if not sentences:
        return ""
    query = set(re.findall(r"[a-z0-9]+", message.lower())) - {
        "a",
        "an",
        "are",
        "for",
        "is",
        "me",
        "please",
        "summarize",
        "the",
        "what",
        "when",
    }
    return max(
        sentences,
        key=lambda sentence: len(query & set(re.findall(r"[a-z0-9]+", sentence.lower()))),
    )


def create_chatbot_app(
    scanner: Scanner,
    identities: Mapping[str, HostAuthority],
    catalog: ResourceCatalog,
    documents: Mapping[str, str],
    output_guard: OutputGuard | None = None,
) -> FastAPI:
    """Keys and authorities originate in the host, never the request body.

    This local reference host intentionally handles only read-and-summarize. It
    never passes arbitrary agent-generated tool calls to the executor.
    """
    if not identities or any(len(key) < 32 for key in identities):
        raise ValueError("Host identities need 32+ character service credentials")
    app = FastAPI(title="kjnlae synthetic host chatbot")
    app.add_middleware(LimitsMiddleware, rate=60)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"]
    )
    actions = ActionGateway()
    executor = GuardedExecutor(actions, catalog)
    outputs = output_guard or OutputGuard()

    def resolve(header: str | None) -> HostAuthority:
        supplied = (header or "").removeprefix("Bearer ")
        found: HostAuthority | None = None
        for key, authority in identities.items():
            if header and header.startswith("Bearer ") and hmac.compare_digest(supplied, key):
                found = authority
        if found is None:
            raise HTTPException(401, "Authentication required")
        return found

    @app.post("/chat", response_model=ChatResult)
    def chat(request: ChatRequest, authorization: str | None = Header(default=None)) -> ChatResult:
        authority = resolve(authorization)
        record = catalog.resolve(request.resource)
        action = ProposedAction(
            tool="read_document", tenant=authority.tenant, resource=request.resource
        )
        # Check the host grant before retrieving text. Unknown or cross-tenant
        # resources receive the same denial without a scanner call.
        eligible = (
            record is not None
            and record.tenant == authority.tenant
            and request.resource in documents
            and any(
                grant.permits(action, authority.principal, record.version)
                for grant in authority.grants
            )
        )
        if not eligible:
            return ChatResult(
                detection_decision="NOT_EVALUATED",
                action_status="DENIED",
                output_decision="NOT_ATTEMPTED",
            )
        source = documents[request.resource]
        scan = scanner.scan(source, source="retrieved_document")
        if scan.policy_decision != "ALLOW":
            return ChatResult(
                detection_decision=scan.policy_decision,
                action_status="DENIED",
                output_decision="NOT_ATTEMPTED",
            )
        result = executor.execute(
            action,
            authority,
            lambda _: "Document excerpt: " + _excerpt_for(request.message, source),
            controls_ready=True,
        )
        if result.status != "EXECUTED" or result.value is None:
            return ChatResult(
                detection_decision=scan.policy_decision,
                action_status=result.status,
                output_decision="NOT_ATTEMPTED",
            )
        released = outputs.release(result.value, None, None, [request.resource], authority, catalog)
        return ChatResult(
            detection_decision=scan.policy_decision,
            action_status=result.status,
            output_decision=released.decision,
            answer=result.value if released.decision == "ALLOW" else None,
        )

    return app
