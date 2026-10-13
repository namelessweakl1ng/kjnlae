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
