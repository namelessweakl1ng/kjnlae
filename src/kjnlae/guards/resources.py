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
    tool: Operation
    tenant: str = Field(min_length=1, max_length=128)
    resource: str = Field(min_length=1, max_length=128)
    destination: str | None = Field(default=None, max_length=254)
    parameters: dict[str, str] = Field(default_factory=dict, max_length=8)


@dataclass(frozen=True)
class ResourceRecord:
    id: str
    tenant: str
    owner: str
    version: int
    sensitive: bool = True
    department: str = ""


@dataclass(frozen=True)
class ResourceGrant:
    principal: str
    tenant: str
    resource: str
    operation: Operation
    version: int
    expires_at: float
    destinations: frozenset[str] = frozenset()

    def permits(self, action: ProposedAction, principal: str, version: int) -> bool:
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
    principal: str
    tenant: str
    task: str
    allowed_tools: frozenset[Operation]
    grants: tuple[ResourceGrant, ...]
    destinations: frozenset[str] = frozenset()


class ResourceCatalog:
    def __init__(self, records: tuple[ResourceRecord, ...] = ()) -> None:
        self._records = {record.id: record for record in records}
        self._lock = threading.RLock()

    def resolve(self, resource: str) -> ResourceRecord | None:
        with self._lock:
            return self._records.get(resource)

    def replace(self, record: ResourceRecord) -> None:
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
