"""Environment configuration is trusted deployment input, never an API request."""

import json
import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path

from kjnlae.guards.actions import Authority, Grant
from kjnlae.guards.resources import (
    HostAuthority,
    Operation,
    ResourceCatalog,
    ResourceGrant,
    ResourceRecord,
)
from kjnlae.schemas import Action, StrictModel


class AuthorityFile(StrictModel):
    principal: str
    owned_resources: frozenset[str]
    destinations: frozenset[str] = frozenset()
    actions: list[Action]


class V2GrantFile(StrictModel):
    resource: str
    operation: Operation
    version: int
    expires_in_seconds: int = 3600
    destinations: frozenset[str] = frozenset()


class V2AuthorityFile(StrictModel):
    principal: str
    tenant: str
    task: str
    allowed_tools: frozenset[Operation]
    grants: tuple[V2GrantFile, ...]
    destinations: frozenset[str] = frozenset()
    resources: tuple[ResourceRecord, ...]


@dataclass(frozen=True)
class Settings:
    production: bool = False
    api_key: str = ""
    database: str = "var/audit.db"
    retention: int = 500
    rate_limit: int = 60
    cors_origins: tuple[str, ...] = ()
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "testserver")
    authority_path: str = ""
    authority_v2_path: str = ""
    model_dir: str = ""
    model_hash: str = ""
    output_hosts: frozenset[str] = frozenset()
    output_secrets: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.production and len(self.api_key) < 32:
            raise ValueError("Production requires an API key with at least 32 characters")
        if self.production and "*" in self.cors_origins:
            raise ValueError("Wildcard production CORS forbidden")
        if self.production and (not self.model_dir or not self.model_hash):
            raise ValueError("Production requires a pinned local fine-tuned model artifact")
        if not 1 <= self.rate_limit <= 10000:
            raise ValueError("Invalid rate limit")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            production=os.getenv("KJNLAE_ENV") == "production",
            api_key=os.getenv("KJNLAE_API_KEY", ""),
            database=os.getenv("KJNLAE_DATABASE", "var/audit.db"),
            retention=int(os.getenv("KJNLAE_RETENTION", "500")),
            rate_limit=int(os.getenv("KJNLAE_RATE_LIMIT", "60")),
            cors_origins=tuple(filter(None, os.getenv("KJNLAE_CORS_ORIGINS", "").split(","))),
            allowed_hosts=tuple(
                os.getenv("KJNLAE_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
            ),
            authority_path=os.getenv("KJNLAE_AUTHORITY_FILE", ""),
            authority_v2_path=os.getenv("KJNLAE_AUTHORITY_V2_FILE", ""),
            model_dir=os.getenv("KJNLAE_MODEL_DIR", ""),
            model_hash=os.getenv("KJNLAE_MODEL_HASH", ""),
            output_hosts=frozenset(filter(None, os.getenv("KJNLAE_OUTPUT_HOSTS", "").split(","))),
            output_secrets=tuple(json.loads(os.getenv("KJNLAE_OUTPUT_SECRETS_JSON", "[]"))),
        )

    def authority(self) -> Authority:
        if not self.authority_path:
            # No permissions by default, including development mode.
            return Authority("api-service" if self.api_key else "local-analysis", frozenset(), ())
        cfg = AuthorityFile.model_validate_json(Path(self.authority_path).read_text())
        return Authority(
            cfg.principal,
            cfg.owned_resources,
            tuple(Grant(a) for a in cfg.actions),
            cfg.destinations,
        )

    def authority_v2(self) -> tuple[HostAuthority, ResourceCatalog]:
        if not self.authority_v2_path:
            return HostAuthority(
                "api-service" if self.api_key else "local-analysis",
                "local",
                "analysis",
                frozenset(),
                (),
            ), ResourceCatalog()
        path = Path(self.authority_v2_path)
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or metadata.st_size > 32768:
            raise ValueError("Authority file must be regular and bounded")
        if self.production and metadata.st_mode & 0o077:
            raise ValueError("Production authority file must have mode 0600")
        cfg = V2AuthorityFile.model_validate_json(path.read_text())
        if not cfg.principal or not cfg.tenant or not cfg.task:
            raise ValueError("Authority identity, tenant and task required")
        if any(record.tenant != cfg.tenant for record in cfg.resources):
            raise ValueError("Cross-tenant resource in authority file")
        if len({record.id for record in cfg.resources}) != len(cfg.resources):
            raise ValueError("Duplicate resource IDs")
        records = {record.id: record for record in cfg.resources}
        grants = []
        for grant in cfg.grants:
            record = records.get(grant.resource)
            if (
                record is None
                or grant.version != record.version
                or not 1 <= grant.expires_in_seconds <= 86400
            ):
                raise ValueError("Invalid grant resource, version or expiry")
            grants.append(
                ResourceGrant(
                    cfg.principal,
                    cfg.tenant,
                    grant.resource,
                    grant.operation,
                    grant.version,
                    time.time() + grant.expires_in_seconds,
                    grant.destinations,
                )
            )
        return HostAuthority(
            cfg.principal, cfg.tenant, cfg.task, cfg.allowed_tools, tuple(grants), cfg.destinations
        ), ResourceCatalog(cfg.resources)
