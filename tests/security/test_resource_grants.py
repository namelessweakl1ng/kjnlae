import time

import pytest
from pydantic import ValidationError

from kjnlae.guards.actions import ActionGateway
from kjnlae.guards.resources import (
    HostAuthority,
    ProposedAction,
    ResourceCatalog,
    ResourceGrant,
    ResourceRecord,
)


def _setup():
    catalog = ResourceCatalog(
        (
            ResourceRecord("patient-1", "hospital-a", "clinician-1", 2),
            ResourceRecord("patient-2", "hospital-b", "clinician-2", 1),
        )
    )
    authority = HostAuthority(
        "clinician-1",
        "hospital-a",
        "Read assigned patient",
        frozenset({"read_document"}),
        (
            ResourceGrant(
                "clinician-1", "hospital-a", "patient-1", "read_document", 2, time.time() + 300
            ),
        ),
    )
    return catalog, authority


def test_cross_tenant_and_other_patient_denied_despite_model_miss() -> None:
    catalog, authority = _setup()
    gateway = ActionGateway()
    denied = gateway.authorize_v2(
        ProposedAction(tool="read_document", tenant="hospital-b", resource="patient-2"),
        authority,
        catalog,
    )
    assert denied.decision == "BLOCK"
    allowed = gateway.authorize_v2(
        ProposedAction(tool="read_document", tenant="hospital-a", resource="patient-1"),
        authority,
        catalog,
    )
    assert allowed.decision == "ALLOW"


def test_untrusted_identity_and_approval_claims_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ProposedAction(
            tool="read_document",
            tenant="hospital-a",
            resource="patient-1",
            principal="clinician-1",
            approved=True,
        )


def test_resource_version_and_unregistered_tool_denied() -> None:
    catalog, authority = _setup()
    catalog.replace(ResourceRecord("patient-1", "hospital-a", "clinician-1", 3))
    gateway = ActionGateway()
    assert (
        gateway.authorize_v2(
            ProposedAction(tool="read_document", tenant="hospital-a", resource="patient-1"),
            authority,
            catalog,
        ).decision
        == "BLOCK"
    )
    assert (
        gateway.authorize_v2(
            ProposedAction(tool="admin", tenant="hospital-a", resource="patient-1"),
            authority,
            catalog,
        ).decision
        == "BLOCK"
    )


def test_same_resource_id_is_owned_independently_by_each_tenant() -> None:
    catalog = ResourceCatalog(
        (
            ResourceRecord("shared-name", "hospital-a", "clinician-a", 1),
            ResourceRecord("shared-name", "hospital-b", "clinician-b", 2),
        )
    )
    assert catalog.resolve("shared-name") is None
    assert catalog.resolve("shared-name", "hospital-a") == ResourceRecord(
        "shared-name", "hospital-a", "clinician-a", 1
    )
    gateway = ActionGateway()
    for tenant, principal, version in (
        ("hospital-a", "clinician-a", 1),
        ("hospital-b", "clinician-b", 2),
    ):
        authority = HostAuthority(
            principal,
            tenant,
            "Read assigned patient",
            frozenset({"read_document"}),
            (
                ResourceGrant(
                    principal, tenant, "shared-name", "read_document", version, time.time() + 300
                ),
            ),
        )
        action = ProposedAction(tool="read_document", tenant=tenant, resource="shared-name")
        assert gateway.authorize_v2(action, authority, catalog).decision == "ALLOW"
        other_tenant = "hospital-b" if tenant == "hospital-a" else "hospital-a"
        assert (
            gateway.authorize_v2(
                action.model_copy(update={"tenant": other_tenant}), authority, catalog
            ).decision
            == "BLOCK"
        )
