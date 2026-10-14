"""Synthetic host-owned approval flow. No external tool or account is contacted."""

import time

from kjnlae.guards.actions import ActionGateway
from kjnlae.guards.resources import (
    HostAuthority,
    ProposedAction,
    ResourceCatalog,
    ResourceGrant,
    ResourceRecord,
)

action = ProposedAction(
    tool="send_email",
    tenant="demo",
    resource="public",
    destination="bob@example.test",
    parameters={"subject": "Summary", "body": "Public schedule"},
)
catalog = ResourceCatalog((ResourceRecord("public", "demo", "alice", 1, sensitive=False),))
# Trusted host code builds this from authenticated identity and current resource state.
authority = HostAuthority(
    "alice",
    "demo",
    "Send public schedule",
    frozenset({"send_email"}),
    (
        ResourceGrant(
            "alice",
            "demo",
            "public",
            "send_email",
            1,
            time.time() + 300,
            frozenset({"bob@example.test"}),
        ),
    ),
    frozenset({"bob@example.test"}),
)
gateway = ActionGateway()
print(gateway.authorize_v2(action, authority, catalog).model_dump())  # REQUIRE_REVIEW
# A trusted host must authenticate a distinct reviewer and display this exact action.
token = gateway.approve_v2(action, authority, catalog, reviewer="reviewer")
print(gateway.authorize_v2(action, authority, catalog, approval_token=token).model_dump())
print(
    gateway.authorize_v2(action, authority, catalog, approval_token=token).model_dump()
)  # replay denied
