import time

import pytest
from pydantic import ValidationError

from kjnlae.guards.actions import ActionGateway, Authority, Grant
from kjnlae.guards.output import OutputGuard
from kjnlae.schemas import Action, ActionRequest


def authority(action):
    return Authority(
        principal="alice",
        owned_resources=frozenset({"doc"}),
        grants=(Grant(action=action),),
        destinations=frozenset({"bob@example.test"}),
    )


def test_authorized_read_and_denied_privileged_action():
    read = Action(tool="read_document", resource="doc")
    gateway = ActionGateway()
    assert gateway.authorize(read, authority(read)).decision == "ALLOW"
    assert (
        gateway.authorize(Action(tool="admin", resource="doc"), authority(read)).decision == "BLOCK"
    )


def test_ownership_intent_and_recipient_are_independent():
    action = Action(tool="send_email", resource="doc", destination="evil@example.test")
    assert ActionGateway().authorize(action, authority(action)).decision == "BLOCK"
    other = Action(tool="read_document", resource="other")
    assert ActionGateway().authorize(other, authority(other)).decision == "BLOCK"


def test_approval_exact_binding_expiry_and_one_use():
    action = Action(tool="send_email", resource="doc", destination="bob@example.test")
    ctx = authority(action)
    gateway = ActionGateway(approval_ttl=0.02)
    assert gateway.authorize(action, ctx).decision == "REQUIRE_REVIEW"
    token = gateway.approve(action, ctx)
    changed = action.model_copy(update={"parameters": {"body": "changed"}})
    assert gateway.authorize(changed, ctx, token).decision != "ALLOW"
    assert gateway.authorize(action, ctx, token).decision == "ALLOW"
    assert gateway.authorize(action, ctx, token).decision != "ALLOW"
    token = gateway.approve(action, ctx)
    time.sleep(0.03)
    assert gateway.authorize(action, ctx, token).decision != "ALLOW"


def test_approval_cannot_expand_permission_or_forge_identity():
    action = Action(tool="admin", resource="doc")
    with pytest.raises(ValueError):
        ActionGateway().approve(action, authority(action))
    with pytest.raises(ValidationError):
        ActionRequest.model_validate(
            {"action": action.model_dump(), "principal": "admin", "approved": True}
        )


def test_required_control_failure_closes_writes():
    action = Action(tool="send_email", resource="doc", destination="bob@example.test")
    ctx = authority(action)
    gateway = ActionGateway()
    token = gateway.approve(action, ctx)
    assert gateway.authorize(action, ctx, token, controls_ready=False).decision == "BLOCK"
    read = Action(tool="read_document", resource="doc")
    assert gateway.authorize(read, authority(read), controls_ready=False).decision == "WARN"


def test_output_exact_secrets_links_and_schema():
    guard = OutputGuard(
        secrets=("mock-secret-123",),
        allowed_hosts=frozenset({"example.test"}),
        allowed_fields=frozenset({"summary"}),
    )
    assert guard.inspect("mock-secret-123").decision == "BLOCK"
    assert guard.inspect("[click](https://evil.test)").decision == "BLOCK"
    assert guard.inspect("https://example.test.evil.test").decision == "BLOCK"
    assert guard.inspect("ok", {"command": "run"}).decision == "BLOCK"
    assert guard.inspect("https://example.test/path", {"summary": "ok"}).decision == "ALLOW"


def test_output_protocol_relative_and_unsupported_links():
    guard = OutputGuard(allowed_hosts=frozenset({"example.test"}))
    assert guard.inspect("[click](//evil.test/path)").decision == "BLOCK"
    assert guard.inspect('<a href="file:///etc/passwd">open</a>').decision == "BLOCK"
    assert guard.inspect('<a href="https://example.test">safe</a>').decision == "ALLOW"


def test_approval_principal_binding():
    action = Action(tool="delete_document", resource="doc")
    ctx = authority(action)
    gateway = ActionGateway()
    token = gateway.approve(action, ctx)
    other = Authority("mallory", ctx.owned_resources, ctx.grants, ctx.destinations)
    assert gateway.authorize(action, other, token).decision == "REQUIRE_REVIEW"
