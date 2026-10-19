import time

from kjnlae.guards.actions import ActionGateway
from kjnlae.guards.executor import GuardedExecutor
from kjnlae.guards.resources import (
    HostAuthority,
    ProposedAction,
    ResourceCatalog,
    ResourceGrant,
    ResourceRecord,
)


def _case():
    action = ProposedAction(
        tool="send_email",
        tenant="company-a",
        resource="report-1",
        destination="allowed.example",
        parameters={"body": "summary"},
    )
    catalog = ResourceCatalog((ResourceRecord("report-1", "company-a", "alice", 4),))
    authority = HostAuthority(
        "alice",
        "company-a",
        "Send approved report",
        frozenset({"send_email"}),
        (
            ResourceGrant(
                "alice",
                "company-a",
                "report-1",
                "send_email",
                4,
                time.time() + 300,
                frozenset({"allowed.example"}),
            ),
        ),
        frozenset({"allowed.example"}),
    )
    return action, catalog, authority


def test_exact_approval_executes_once_and_replay_denies() -> None:
    action, catalog, authority = _case()
    gateway = ActionGateway()
    executor = GuardedExecutor(gateway, catalog)
    calls = []
    token = gateway.approve_v2(action, authority, catalog, reviewer="human-reviewer")
    first = executor.execute(
        action, authority, lambda proposed: calls.append(proposed) or "sent", approval_token=token
    )
    second = executor.execute(
        action, authority, lambda proposed: calls.append(proposed) or "sent", approval_token=token
    )
    assert first.status == "EXECUTED"
    assert second.status == "DENIED"
    assert len(calls) == 1


def test_changed_parameters_and_resource_version_never_execute() -> None:
    action, catalog, authority = _case()
    gateway = ActionGateway()
    executor = GuardedExecutor(gateway, catalog)
    calls = []
    token = gateway.approve_v2(action, authority, catalog, reviewer="human-reviewer")
    changed = action.model_copy(update={"parameters": {"body": "different"}})
    assert (
        executor.execute(changed, authority, lambda a: calls.append(a), approval_token=token).status
        == "DENIED"
    )
    catalog.replace(ResourceRecord("report-1", "company-a", "alice", 5))
    assert (
        executor.execute(action, authority, lambda a: calls.append(a), approval_token=token).status
        == "DENIED"
    )
    assert calls == []


def test_model_failure_blocks_sensitive_callback() -> None:
    action, catalog, authority = _case()
    calls = []
    result = GuardedExecutor(ActionGateway(), catalog).execute(
        action, authority, lambda a: calls.append(a), controls_ready=False
    )
    assert result.status == "DENIED"
    assert calls == []


def test_catalog_change_between_authorization_and_execution_denies() -> None:
    action, catalog, authority = _case()

    class RacingGateway(ActionGateway):
        def authorize_v2(self, *args, **kwargs):
            result = super().authorize_v2(*args, **kwargs)
            if result.decision == "ALLOW":
                catalog.replace(ResourceRecord("report-1", "company-a", "alice", 5))
            return result

    gateway = RacingGateway()
    token = gateway.approve_v2(action, authority, catalog, reviewer="human-reviewer")
    calls = []
    result = GuardedExecutor(gateway, catalog).execute(
        action, authority, lambda a: calls.append(a), approval_token=token
    )
    assert result.status == "DENIED"
    assert calls == []


def test_shared_id_wrong_tenant_never_reaches_callback() -> None:
    action, catalog, authority = _case()
    catalog.replace(ResourceRecord("report-1", "company-b", "bob", 4))
    calls = []
    executor = GuardedExecutor(ActionGateway(), catalog)
    denied = executor.execute(
        action.model_copy(update={"tenant": "company-b"}),
        authority,
        lambda proposed: calls.append(proposed),
    )
    assert denied.status == "DENIED"
    assert calls == []
    token = executor.gateway.approve_v2(action, authority, catalog, reviewer="reviewer")
    allowed = executor.execute(
        action, authority, lambda proposed: calls.append(proposed), approval_token=token
    )
    assert allowed.status == "EXECUTED"
    assert calls == [action]
