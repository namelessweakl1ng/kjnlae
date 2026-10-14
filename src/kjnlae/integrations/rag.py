"""Local RAG boundary: ACL precedes model inspection and generation."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from kjnlae.context import TrustedSecurityContext
from kjnlae.guards.resources import ProposedAction, ResourceCatalog, ResourceGrant
from kjnlae.schemas_v2 import InspectionResultV2


class Scanner(Protocol):
    """Small scanner contract so retrieval does not depend on HTTP."""

    def scan(self, text: str, **context: object) -> InspectionResultV2: ...


@dataclass(frozen=True)
class RagChunk:
    """Retrieved document text with host-owned tenant/resource identity."""

    id: str
    resource: str
    tenant: str
    title: str
    text: str


@dataclass(frozen=True)
class RetrievalResult:
    """Authorized, scanned chunks and IDs withheld after scanning."""

    chunks: tuple[RagChunk, ...]
    citations: tuple[str, ...]
    withheld: tuple[str, ...]


class RagGateway:
    """Apply resource grants before exposing retrieved text to the model."""

    def __init__(
        self, chunks: Sequence[RagChunk], guard: Scanner, catalog: ResourceCatalog
    ) -> None:
        self.chunks = tuple(chunks)
        self.guard = guard
        self.catalog = catalog

    def retrieve(
        self,
        query: str,
        context: TrustedSecurityContext,
        grants: tuple[ResourceGrant, ...],
    ) -> RetrievalResult:
        """Retrieve by title, then enforce ACL and complete model inspection."""
        if not 1 <= len(query) <= 4096:
            raise ValueError("Query size outside supported range")
        if len(self.chunks) > 256:
            raise ValueError("Retrieval set exceeds complete inspection budget")
        # Word matching only selects candidate titles; it is not injection detection.
        words = set(re.findall(r"\w+", query.casefold()))
        accepted: list[RagChunk] = []
        withheld: list[str] = []
        for chunk in self.chunks:
            if chunk.tenant != context.tenant:
                continue
            if not words.intersection(re.findall(r"\w+", chunk.title.casefold())):
                continue
            record = self.catalog.resolve(chunk.resource)
            if record is None or record.tenant != context.tenant:
                continue
            action = ProposedAction(
                tool="read_document", tenant=context.tenant, resource=chunk.resource
            )
            if not any(g.permits(action, context.principal, record.version) for g in grants):
                continue
            result = self.guard.scan(chunk.text, source="retrieved_document")
            if result.policy_decision != "ALLOW":
                withheld.append(chunk.id)
            else:
                accepted.append(chunk)
        return RetrievalResult(tuple(accepted), tuple(c.id for c in accepted), tuple(withheld))
