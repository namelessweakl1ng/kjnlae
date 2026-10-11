"""Environment configuration is trusted deployment input, never an API request."""

import json
import os
from dataclasses import dataclass
from pathlib import Path

from kjnlae.guards.actions import Authority, Grant
from kjnlae.schemas import Action, StrictModel


class AuthorityFile(StrictModel):
    principal: str
    owned_resources: frozenset[str]
    destinations: frozenset[str] = frozenset()
    actions: list[Action]


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
    model_id: str = ""
    model_revision: str = ""
    model_label: str = ""
    require_ml: bool = False
    output_hosts: frozenset[str] = frozenset()
    output_secrets: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.production and len(self.api_key) < 32:
            raise ValueError("Production requires an API key with at least 32 characters")
        if self.production and "*" in self.cors_origins:
            raise ValueError("Wildcard production CORS forbidden")
        if self.require_ml and not self.model_id:
            raise ValueError("Required ML needs model configuration")
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
            model_id=os.getenv("KJNLAE_MODEL_ID", ""),
            model_revision=os.getenv("KJNLAE_MODEL_REVISION", ""),
            model_label=os.getenv("KJNLAE_MODEL_LABEL", ""),
            require_ml=os.getenv("KJNLAE_REQUIRE_ML") == "1",
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
