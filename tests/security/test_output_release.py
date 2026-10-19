import base64
import time

from kjnlae.guards.output import OutputGuard
from kjnlae.guards.resources import HostAuthority, ResourceCatalog, ResourceGrant, ResourceRecord


def _authority():
    catalog = ResourceCatalog((ResourceRecord("patient-1", "hospital-a", "doctor", 1),))
    authority = HostAuthority(
        "doctor",
        "hospital-a",
        "Read assigned record",
        frozenset({"read_document"}),
        (
            ResourceGrant(
                "doctor", "hospital-a", "patient-1", "read_document", 1, time.time() + 300
            ),
        ),
    )
    return catalog, authority


def test_output_release_checks_resource_and_recipient() -> None:
    catalog, authority = _authority()
    guard = OutputGuard(secrets=("MOCK-SECRET",), allowed_hosts=frozenset({"example.test"}))
    assert (
        guard.release("Summary", None, None, ["patient-1"], authority, catalog).decision == "ALLOW"
    )
    assert (
        guard.release("Summary", None, "other.invalid", ["patient-1"], authority, catalog).decision
        == "BLOCK"
    )
    assert (
        guard.release("Summary", None, None, ["patient-2"], authority, catalog).decision == "BLOCK"
    )


def test_known_secret_encoded_in_output_is_blocked() -> None:
    catalog, authority = _authority()
    guard = OutputGuard(secrets=("MOCK-SECRET",))
    encoded = base64.b64encode(b"MOCK-SECRET").decode()
    assert guard.release(encoded, None, None, ["patient-1"], authority, catalog).decision == "BLOCK"
    assert (
        guard.release("MOCK&#45;SECRET", None, None, ["patient-1"], authority, catalog).decision
        == "BLOCK"
    )
    assert guard.inspect("MOCK<!-- -->-SECRET").decision == "BLOCK"
    assert guard.inspect("MOCK<span></span>-SECRET").decision == "BLOCK"
    assert guard.inspect("<!-- hidden -->").decision == "ALLOW"


def test_shared_id_output_release_requires_exact_tenant_grants_and_controls() -> None:
    catalog = ResourceCatalog(
        (ResourceRecord("shared", "north", "alice", 3), ResourceRecord("shared", "south", "bob", 3))
    )
    guard = OutputGuard()
    north = HostAuthority(
        "alice",
        "north",
        "Read report",
        frozenset({"read_document"}),
        (ResourceGrant("alice", "north", "shared", "read_document", 3, time.time() + 300),),
    )
    assert guard.release("North report", None, None, ["shared"], north, catalog).decision == "ALLOW"
    assert (
        guard.release(
            "North report", None, None, ["shared"], north, catalog, controls_ready=False
        ).decision
        == "BLOCK"
    )
    assert (
        guard.release(
            "North report", None, "elsewhere.invalid", ["shared"], north, catalog
        ).decision
        == "BLOCK"
    )
    south = HostAuthority("bob", "south", "Read report", frozenset({"read_document"}), north.grants)
    assert guard.release("North report", None, None, ["shared"], south, catalog).decision == "BLOCK"
    catalog.replace(ResourceRecord("shared", "north", "alice", 4))
    assert guard.release("North report", None, None, ["shared"], north, catalog).decision == "BLOCK"
