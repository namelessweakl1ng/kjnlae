"""Metadata-only bounded persistence with a replaceable protocol."""

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Protocol


class HistoryStore(Protocol):
    def record(self, result: dict[str, Any], tenant: str = "legacy") -> None: ...
    def list(self, limit: int = 100, tenant: str = "legacy") -> list[dict[str, Any]]: ...
    def clear(self, tenant: str = "legacy") -> None: ...


class SQLiteHistory:
    def __init__(self, path: str, retention: int = 500, max_age_days: int = 7) -> None:
        if not 0 <= retention <= 10000 or not 1 <= max_age_days <= 365:
            raise ValueError("Invalid retention settings")
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Never follow an existing database symlink.
        fd = os.open(target, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        os.chmod(target, 0o600)
        self.path, self.retention, self.max_age_days = path, retention, max_age_days
        self._lock = threading.Lock()
        with sqlite3.connect(path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS scans "
                "(id INTEGER PRIMARY KEY, at REAL NOT NULL, "
                "tenant TEXT NOT NULL DEFAULT 'legacy', metadata TEXT NOT NULL)"
            )
            if "tenant" not in {row[1] for row in conn.execute("PRAGMA table_info(scans)")}:
                conn.execute("ALTER TABLE scans ADD COLUMN tenant TEXT NOT NULL DEFAULT 'legacy'")
            conn.execute("CREATE INDEX IF NOT EXISTS scans_tenant_id ON scans(tenant, id DESC)")

    def _prune(self, conn: sqlite3.Connection) -> None:
        conn.execute("DELETE FROM scans WHERE at < ?", (time.time() - self.max_age_days * 86400,))
        conn.execute(
            "DELETE FROM scans WHERE id NOT IN (SELECT id FROM scans ORDER BY id DESC LIMIT ?)",
            (self.retention,),
        )

    def record(self, result: dict[str, Any], tenant: str = "legacy") -> None:
        # Allowlist: prompts, evidence strings, tasks, destinations and secrets never persist.
        metadata = {
            k: result[k]
            for k in (
                "decision",
                "policy_decision",
                "detection_status",
                "model_status",
                "model_hash",
                "source",
                "source_trust",
                "risk_level",
                "risk_score",
                "detection_mode",
                "policy_id",
                "latency_ms",
                "inspection_complete",
            )
            if k in result
        }
        if not tenant or len(tenant) > 128:
            raise ValueError("Trusted tenant required")
        with self._lock, sqlite3.connect(self.path) as conn:
            if self.retention:
                conn.execute(
                    "INSERT INTO scans(at, tenant, metadata) VALUES (?, ?, ?)",
                    (time.time(), tenant, json.dumps(metadata)),
                )
            self._prune(conn)

    def list(self, limit: int = 100, tenant: str = "legacy") -> list[dict[str, Any]]:
        with self._lock, sqlite3.connect(self.path) as conn:
            self._prune(conn)
            rows = conn.execute(
                "SELECT id, at, metadata FROM scans WHERE tenant = ? ORDER BY id DESC LIMIT ?",
                (tenant, max(0, min(limit, 500))),
            ).fetchall()
        return [{"id": r[0], "at": r[1], **json.loads(r[2])} for r in rows]

    def clear(self, tenant: str = "legacy") -> None:
        with self._lock, sqlite3.connect(self.path) as conn:
            conn.execute("DELETE FROM scans WHERE tenant = ?", (tenant,))
