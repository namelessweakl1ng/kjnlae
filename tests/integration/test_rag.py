from kjnlae.context import TrustedSecurityContext
from kjnlae.guards.resources import ResourceCatalog, ResourceGrant, ResourceRecord
from kjnlae.integrations.rag import RagChunk, RagGateway


class StubGuard:
    def __init__(self, decision: str = "ALLOW") -> None:
        self.decision = decision
        self.seen: list[str] = []

    def scan(self, text: str, **context: object):
        self.seen.append(text)
        return type(
            "Scan",
            (),
            {
                "policy_decision": self.decision,
                "detection_status": "INCOMPLETE"
                if self.decision == "REQUIRE_REVIEW"
                else "NO_EVIDENCE_FOUND",
            },
        )()


def test_rag_filters_acl_before_scan_and_retains_host_citations():
    from time import time

    chunks = [
        RagChunk("c1", "public", "acme", "Benefits handbook", "Benefits include leave."),
        RagChunk("c2", "private", "acme", "Benefits private", "Secret salary table"),
        RagChunk("c3", "other", "else", "Benefits", "Other tenant"),
    ]
    catalog = ResourceCatalog(
        tuple(ResourceRecord(c.resource, c.tenant, "host", 1) for c in chunks)
    )
    grant = ResourceGrant("alice", "acme", "public", "read_document", 1, time() + 60)
    guard = StubGuard()
    result = RagGateway(chunks, guard, catalog).retrieve(
        "benefits", TrustedSecurityContext("alice", "acme", "summarize"), (grant,)
    )
    assert [c.id for c in result.chunks] == ["c1"]
    assert result.citations == ("c1",)
    assert guard.seen == ["Benefits include leave."]


def test_rag_withholds_scanner_block_and_incomplete():
    from time import time

    chunk = RagChunk("c1", "public", "acme", "Benefits", "Poisoned page")
    catalog = ResourceCatalog((ResourceRecord("public", "acme", "host", 1),))
    grant = ResourceGrant("alice", "acme", "public", "read_document", 1, time() + 60)
    for decision in ("BLOCK", "REQUIRE_REVIEW"):
        result = RagGateway((chunk,), StubGuard(decision), catalog).retrieve(
            "benefits", TrustedSecurityContext("alice", "acme", "summarize"), (grant,)
        )
        assert result.chunks == ()
        assert result.withheld == ("c1",)
