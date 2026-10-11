"""Trusted host integration, no real side effects. Run: python examples/authorization.py."""

from kjnlae.guards.actions import ActionGateway, Authority, Grant
from kjnlae.schemas import Action

# Construct only from an authenticated user task through trusted application logic.
action = Action(
    tool="send_email",
    resource="public",
    destination="bob@example.test",
    parameters={"subject": "Summary", "body": "Public schedule"},
)
authority = Authority(
    "alice", frozenset({"public"}), (Grant(action),), frozenset({"bob@example.test"})
)
gateway = ActionGateway()
print(gateway.authorize(action, authority).model_dump())  # REQUIRE_REVIEW
# In a real host, authenticate the reviewer and show THIS exact action before this call.
# This example represents that trusted ceremony; no API caller can assert it occurred.
token = gateway.approve(action, authority)
print(gateway.authorize(action, authority, token).model_dump())  # ALLOW
print(gateway.authorize(action, authority, token).model_dump())  # Replay requires review
