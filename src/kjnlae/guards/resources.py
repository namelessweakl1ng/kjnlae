"""Host-owned tenant resources and grants. Agent text cannot mint these objects."""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, TypeVar

from pydantic import Field

from kjnlae.schemas_v2 import StrictV2

Operation = Literal["read_document", "send_email", "delete_document", "admin"]
T = TypeVar("T")


class ProposedAction(StrictV2):
    """Untrusted proposed tool call; fields alone never establish permission."""

    tool: Operation
    tenant: str = Field(min_length=1, max_length=128)
    resource: str = Field(min_length=1, max_length=128)
    destination: str | None = Field(default=None, max_length=254)
    parameters: dict[str, str] = Field(default_factory=dict, max_length=8)


@dataclass(frozen=True)
class ResourceRecord:
    """Current host-owned resource identity and version for authorization."""

    id: str
    tenant: str
    owner: str
    version: int
    sensitive: bool = True
    department: str = ""


@dataclass(frozen=True)
class ResourceGrant:
    """Short-lived, exact permission issued by trusted application code."""

    principal: str
    tenant: str
    resource: str
    operation: Operation
    version: int
    expires_at: float
    destinations: frozenset[str] = frozenset()

    def permits(self, action: ProposedAction, principal: str, version: int) -> bool:
        """Match principal, tenant, operation, resource version and destination."""
        return (
            self.principal == principal
            and self.tenant == action.tenant
            and self.resource == action.resource
            and self.operation == action.tool
            and self.version == version
            and self.expires_at > time.time()
            and (action.destination is None or action.destination in self.destinations)
        )


@dataclass(frozen=True)
class HostAuthority:
    """Authenticated host context; never constructed from model or scan text."""

    principal: str
    tenant: str
    task: str
    allowed_tools: frozenset[Operation]
    grants: tuple[ResourceGrant, ...]
    destinations: frozenset[str] = frozenset()


class ResourceCatalog:
    """Thread-safe in-memory resource catalog used by the synthetic hosts."""

    def __init__(self, records: tuple[ResourceRecord, ...] = ()) -> None:
        self._records = {record.id: record for record in records}
        self._lock = threading.RLock()

    def resolve(self, resource: str) -> ResourceRecord | None:
        """Return the current record for an exact resource identifier."""
        with self._lock:
            return self._records.get(resource)

    def replace(self, record: ResourceRecord) -> None:
        """Advance a record so grants and approvals for older versions expire."""
        with self._lock:
            self._records[record.id] = record

    def run_if_current(
        self, expected: ResourceRecord, callback: Callable[[], T]
    ) -> tuple[bool, T | None]:
        """Local synthetic adapter hook; external stores need their own transaction."""
        with self._lock:
            record = self._records.get(expected.id)
            if record != expected:
                return False, None
            return True, callback()
