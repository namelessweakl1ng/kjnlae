"""Prepare blinded candidate cases for later independent human label review."""

import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kjnlae.schemas import Source


def verify_git_checkout(root: Path, expected_revision: str) -> None:
    """Require an exact, clean tracked source revision before importing cases."""
    if not re.fullmatch(r"[0-9a-f]{40}", expected_revision) or root.is_symlink():
        raise ValueError("Source revision or checkout is invalid")
    try:
        revision = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        changes = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Source checkout cannot be verified") from exc
    if revision != expected_revision:
        raise ValueError("Source checkout revision mismatch")
    if changes:
        raise ValueError("Source checkout has modified tracked files")


@dataclass(frozen=True)
class Candidate:
    id: str
    text: str
    source: Source
    legitimate_task: str
    upstream_label: int | None
    provenance: str


def _normalized(text: str) -> str:
    return re.sub(r"[^\w]+", "", unicodedata.normalize("NFKC", text).casefold())


def _candidate_id(prefix: str, text: str) -> str:
    return f"{prefix}-{hashlib.sha256(_normalized(text).encode('utf-8')).hexdigest()[:24]}"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(dict(record), ensure_ascii=False, sort_keys=True) + "\n")
    path.chmod(0o600)


def _private_permissions_supported() -> bool:
    return os.name == "posix"


def build_review_bundle(
    candidates: Iterable[Candidate],
    output: Path,
    *,
    source_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Write blinded review rows and a separate provenance key without overwriting."""
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Annotation bundle already exists: {output}")
    rows = list(candidates)
    if not 1 <= len(rows) <= 10000:
        raise ValueError("Annotation bundle needs 1..10000 candidate rows")
    ids: set[str] = set()
    normalized: set[str] = set()
    for row in rows:
        text = _normalized(row.text)
        if (
            not row.id
            or not text
            or len(row.text) > 32768
            or len(row.legitimate_task) > 4096
            or type(row.upstream_label) not in {int, type(None)}
            or row.upstream_label not in {0, 1, None}
        ):
            raise ValueError("Invalid annotation candidate")
        if row.id in ids or text in normalized:
            raise ValueError("Annotation candidates contain duplicate ids or normalized text")
        ids.add(row.id)
        normalized.add(text)
    if not _private_permissions_supported():
        raise OSError("Private annotation bundle requires POSIX owner-only permissions")
    random.Random(42).shuffle(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".kjnlae-review-", dir=output.parent))
    try:
        review = temporary / "review.jsonl"
        provenance = temporary / "sealed-provenance.jsonl"
        _write_jsonl(
            review,
            (
                {
                    "id": row.id,
                    "text": row.text,
                    "source": row.source,
                    "legitimate_task": row.legitimate_task,
                    "review_label": None,
                    "review_reason": "",
                    "reviewer_id": "",
                }
                for row in rows
            ),
        )
        _write_jsonl(
            provenance,
            (
                {
                    "id": row.id,
                    "upstream_label": row.upstream_label,
                    "provenance": row.provenance,
                }
                for row in rows
            ),
        )
        manifest: dict[str, Any] = {
            "status": "PENDING_HUMAN_REVIEW",
            "candidate_count": len(rows),
            "source_counts": dict(sorted(Counter(row.source for row in rows).items())),
            "review_sha256": _sha256(review),
            "sealed_provenance_sha256": _sha256(provenance),
            "independent_family_count": None,
            "source_metadata": dict(source_metadata or {}),
            "note": "Candidate rows are not adjudicated labels or a final evaluation split.",
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
        (temporary / "manifest.json").chmod(0o600)
        if output.exists() or output.is_symlink():
            raise FileExistsError(f"Annotation bundle already exists: {output}")
        temporary.rename(output)
        return manifest
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def agentdojo_candidates(runs: Path, *, stats: dict[str, int] | None = None) -> list[Candidate]:
    """Extract distinct injected tool text with its legitimate user task."""
    if runs.is_symlink() or not runs.is_dir():
        raise ValueError("AgentDojo runs directory missing or linked")
    paths = sorted(runs.rglob("injection_task_*.json"))
    if not 1 <= len(paths) <= 40000:
        raise ValueError("AgentDojo run count outside bounded range")
    if stats is not None:
        stats["run_files"] = len(paths)
        stats["runs_without_legitimate_task"] = 0
    found: dict[str, Candidate] = {}
    for path in paths:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError(f"AgentDojo run missing, linked or oversized: {path}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("injections"), dict):
            raise ValueError(f"AgentDojo run has no injection mapping: {path}")
        task = ""
        for message in raw.get("messages", []):
            if isinstance(message, dict) and message.get("role") == "user":
                content = message.get("content")
                if isinstance(content, str):
                    task = content
                elif isinstance(content, list):
                    task = " ".join(
                        item["content"]
                        for item in content
                        if isinstance(item, dict) and isinstance(item.get("content"), str)
                    )
                break
        if not task or len(task) > 4096:
            if stats is not None:
                stats["runs_without_legitimate_task"] += 1
            continue
        for slot, text in raw["injections"].items():
            if not isinstance(slot, str) or not isinstance(text, str):
                raise ValueError(f"AgentDojo injection slot malformed: {path}")
            normalized = _normalized(text)
            if not normalized or len(text) > 32768:
                raise ValueError(f"AgentDojo injected text empty or oversized: {path}")
            found.setdefault(
                normalized,
                Candidate(
                    _candidate_id("agentdojo", text),
                    text,
                    "tool_response",
                    task,
                    1,
                    f"agentdojo:{path.relative_to(runs)}:{slot}:{_sha256(path)}",
                ),
            )
    if stats is not None:
        stats["unique_candidate_texts"] = len(found)
    return list(found.values())


def import_bipia_file(path: Path, *, source: Source, expected_sha256: str) -> list[Candidate]:
    """Import unpoisoned BIPIA TEST contexts with a pinned file digest."""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("BIPIA expected SHA-256 must be lowercase hex")
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("BIPIA source missing, linked or oversized")
    if _sha256(path) != expected_sha256:
        raise ValueError("BIPIA source SHA-256 mismatch")
    found: dict[str, Candidate] = {}
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raise ValueError("BIPIA row must be an object")
        text = raw.get("context")
        if isinstance(text, list) and all(isinstance(line, str) for line in text):
            text = "\n".join(text)
        task = raw.get("question", "")
        if not task and "error" in raw and "code" in raw:
            task = "Suggest a repair for the shown exception and code."
        if not isinstance(text, str) or not isinstance(task, str):
            raise ValueError("BIPIA context or question malformed")
        normalized = _normalized(text)
        if not normalized or len(text) > 32768 or len(task) > 4096:
            raise ValueError("BIPIA context or question outside supported bounds")
        found.setdefault(
            normalized,
            Candidate(
                _candidate_id("bipia", text),
                text,
                source,
                task,
                0,
                f"bipia:{path.name}:{index}:{expected_sha256}",
            ),
        )
        if index >= 10000:
            raise ValueError("BIPIA source exceeds 10000 rows")
    return list(found.values())


def neuralchemy_candidates(
    records: Iterable[Mapping[str, Any]], *, source_digest: str
) -> list[Candidate]:
    """Keep upstream labels sealed; these mixed-origin labels need adjudication."""
    if not re.fullmatch(r"[0-9a-f]{64}", source_digest):
        raise ValueError("NeurAlchemy source SHA-256 must be lowercase hex")
    found: dict[str, Candidate] = {}
    for index, row in enumerate(records):
        text = row.get("text")
        label = row.get("label")
        if not isinstance(text, str) or type(label) is not int or label not in {0, 1}:
            raise ValueError("NeurAlchemy text or label malformed")
        normalized = _normalized(text)
        if not normalized or len(text) > 32768:
            raise ValueError("NeurAlchemy text outside supported bounds")
        found.setdefault(
            normalized,
            Candidate(
                _candidate_id("neuralchemy", text),
                text,
                "user",
                "Respond to the direct user message without granting new authority.",
                label,
                (
                    f"neuralchemy:{row.get('group_id', index)}:"
                    f"{row.get('category', '')}:{source_digest}"
                ),
            ),
        )
        if index >= 10000:
            raise ValueError("NeurAlchemy source exceeds 10000 rows")
    return list(found.values())
