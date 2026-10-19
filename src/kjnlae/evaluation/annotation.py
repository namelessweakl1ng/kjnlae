"""Prepare blinded candidate cases for later independent human label review."""

import hashlib
import hmac
import json
import os
import random
import re
import secrets
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
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
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
    if Path(top).resolve() != root.resolve():
        raise ValueError("Source checkout is not the repository root")
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
    """Write separate reviewer-only and sealed maintainer packages without overwrite."""
    reviewer_output = output.with_name(output.name + "-reviewer")
    if any(path.exists() or path.is_symlink() for path in (output, reviewer_output)):
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
    temporary = Path(tempfile.mkdtemp(prefix=".kjnlae-sealed-", dir=output.parent))
    review_temporary = Path(tempfile.mkdtemp(prefix=".kjnlae-review-", dir=output.parent))
    try:
        review = review_temporary / "review.jsonl"
        provenance = temporary / "sealed-provenance.jsonl"
        key = secrets.token_bytes(32)
        blinded = [
            ("case-" + hmac.new(key, row.id.encode(), hashlib.sha256).hexdigest(), row)
            for row in rows
        ]
        _write_jsonl(
            review,
            (
                {
                    "id": opaque_id,
                    "text": row.text,
                    "source": row.source,
                    "legitimate_task": row.legitimate_task,
                    "review_label": None,
                    "review_reason": "",
                    "reviewer_id": "",
                }
                for opaque_id, row in blinded
            ),
        )
        _write_jsonl(
            provenance,
            (
                {
                    "id": opaque_id,
                    "original_id": row.id,
                    "upstream_label": row.upstream_label,
                    "provenance": row.provenance,
                    "text_sha256": hashlib.sha256(row.text.encode("utf-8")).hexdigest(),
                }
                for opaque_id, row in blinded
            ),
        )
        review_manifest = {
            "format": "kjnlae-review-v2",
            "status": "PENDING_HUMAN_REVIEW",
            "candidate_count": len(rows),
            "review_sha256": _sha256(review),
            "note": "Unadjudicated candidate texts; no model outputs or upstream labels.",
        }
        review_manifest_file = review_temporary / "manifest.json"
        review_manifest_file.write_text(
            json.dumps(review_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        review_manifest_file.chmod(0o600)
        manifest: dict[str, Any] = {
            "format": "kjnlae-sealed-v2",
            "status": "PENDING_HUMAN_REVIEW",
            "candidate_count": len(rows),
            "source_counts": dict(sorted(Counter(row.source for row in rows).items())),
            "review_sha256": _sha256(review),
            "sealed_provenance_sha256": _sha256(provenance),
            "review_manifest_sha256": _sha256(review_manifest_file),
            "blinding_key_hex": key.hex(),
            "independent_family_count": None,
            "source_metadata": dict(source_metadata or {}),
            "note": "Candidate rows are not adjudicated labels or a final evaluation split.",
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
        (temporary / "manifest.json").chmod(0o600)
        if any(path.exists() or path.is_symlink() for path in (output, reviewer_output)):
            raise FileExistsError(f"Annotation bundle already exists: {output}")
        temporary.rename(output)
        try:
            review_temporary.rename(reviewer_output)
        except OSError:
            shutil.rmtree(output)
            raise
        verify_review_bundle(output, reviewer_output)
        return manifest
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
        if review_temporary.exists():
            shutil.rmtree(review_temporary)


def verify_review_bundle(sealed_dir: Path, reviewer_dir: Path) -> None:
    """Verify byte hashes, private mapping and reviewer-package file allowlist."""
    if not _private_permissions_supported():
        raise OSError("Private annotation bundle requires POSIX owner-only permissions")
    for directory in (sealed_dir, reviewer_dir):
        if not directory.is_dir() or directory.is_symlink() or directory.stat().st_mode & 0o077:
            raise ValueError("Bundle directory is missing, linked or not private")
    if {p.name for p in sealed_dir.iterdir()} != {"manifest.json", "sealed-provenance.jsonl"}:
        raise ValueError("Unexpected sealed bundle files")
    if {p.name for p in reviewer_dir.iterdir()} != {"manifest.json", "review.jsonl"}:
        raise ValueError("Unexpected reviewer bundle files")
    for directory in (sealed_dir, reviewer_dir):
        for path in directory.iterdir():
            if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077:
                raise ValueError("Bundle file is linked, invalid or not private")
    sealed = json.loads((sealed_dir / "manifest.json").read_text())
    reviewer = json.loads((reviewer_dir / "manifest.json").read_text())
    if not isinstance(sealed, dict) or not isinstance(reviewer, dict):
        raise ValueError("Invalid bundle manifests")
    if set(reviewer) != {"format", "status", "candidate_count", "review_sha256", "note"}:
        raise ValueError("Reviewer manifest contains unexpected fields")
    if (
        sealed.get("format") != "kjnlae-sealed-v2"
        or reviewer.get("format") != "kjnlae-review-v2"
        or sealed.get("review_sha256") != _sha256(reviewer_dir / "review.jsonl")
        or reviewer.get("review_sha256") != sealed.get("review_sha256")
        or sealed.get("sealed_provenance_sha256") != _sha256(sealed_dir / "sealed-provenance.jsonl")
        or sealed.get("review_manifest_sha256") != _sha256(reviewer_dir / "manifest.json")
    ):
        raise ValueError("Annotation bundle hash mismatch")
    try:
        key = bytes.fromhex(sealed["blinding_key_hex"])
        review_rows = [
            json.loads(line) for line in (reviewer_dir / "review.jsonl").read_text().splitlines()
        ]
        sealed_rows = [
            json.loads(line)
            for line in (sealed_dir / "sealed-provenance.jsonl").read_text().splitlines()
        ]
        if (
            len(key) != 32
            or len(review_rows) != sealed["candidate_count"]
            or len(sealed_rows) != len(review_rows)
        ):
            raise ValueError("Annotation bundle count mismatch")
        mapping = {row["id"]: row for row in sealed_rows}
        if len(mapping) != len(sealed_rows) or len({row["id"] for row in review_rows}) != len(
            review_rows
        ):
            raise ValueError("Duplicate annotation mapping")
        if set(mapping) != {row["id"] for row in review_rows}:
            raise ValueError("Missing annotation mapping")
        for row in review_rows:
            if set(row) != {
                "id",
                "text",
                "source",
                "legitimate_task",
                "review_label",
                "review_reason",
                "reviewer_id",
            } or not re.fullmatch(r"case-[0-9a-f]{64}", row["id"]):
                raise ValueError("Reviewer row contains unexpected fields or ID")
            entry = mapping[row["id"]]
            expected = (
                "case-" + hmac.new(key, entry["original_id"].encode(), hashlib.sha256).hexdigest()
            )
            if (
                row["id"] != expected
                or hashlib.sha256(row["text"].encode()).hexdigest() != entry["text_sha256"]
            ):
                raise ValueError("Invalid annotation mapping")
    except (KeyError, TypeError, AttributeError, UnicodeError) as exc:
        raise ValueError("Malformed annotation mapping") from exc


def agentdojo_candidates(
    runs: Path, *, stats: dict[str, int | str] | None = None, expected_revision: str | None = None
) -> list[Candidate]:
    """Extract only pinned, tracked run JSONs with their legitimate user task."""
    if runs.is_symlink() or not runs.is_dir():
        raise ValueError("AgentDojo runs directory missing or linked")
    root = runs.parent
    try:
        revision = (
            expected_revision
            or subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
        )
        verify_git_checkout(root, revision)
        tree = subprocess.run(
            ["git", "-C", str(root), "ls-tree", "-r", "-z", "HEAD", "--", "runs"],
            check=True,
            capture_output=True,
            timeout=30,
        ).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("AgentDojo tracked file set cannot be verified") from exc
    pinned_blobs: dict[Path, str] = {}
    for entry in tree.split(b"\0"):
        if not entry:
            continue
        header, name = entry.split(b"\t", 1)
        path = Path(os.fsdecode(name))
        if path.name.startswith("injection_task_") and path.suffix == ".json":
            if b"\n" in name or header.split()[0] not in {b"100644", b"100755"}:
                raise ValueError("AgentDojo run path or Git mode is unsupported")
            pinned_blobs[path] = header.split()[2].decode("ascii")
    relative = sorted(pinned_blobs)
    discovered = {path.relative_to(root) for path in runs.rglob("injection_task_*.json")}
    approved = set(relative)
    if discovered - approved:
        raise ValueError("AgentDojo contains untracked or unexpected run files")
    if approved - discovered:
        raise ValueError("AgentDojo tracked run files missing")
    paths = [root / name for name in relative]
    if not 1 <= len(paths) <= 40000:
        raise ValueError("AgentDojo run count outside bounded range")
    if any(
        path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file()
        for path in paths
    ):
        raise ValueError("AgentDojo run missing, linked or outside checkout")
    try:
        hashed = subprocess.run(
            ["git", "hash-object", "--stdin-paths"],
            cwd=root,
            input="\n".join(str(name) for name in relative) + "\n",
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("AgentDojo worktree blobs cannot be verified") from exc
    if len(hashed) != len(relative) or any(
        blob != pinned_blobs[name] for name, blob in zip(relative, hashed, strict=True)
    ):
        raise ValueError("AgentDojo run blob hash differs from pinned commit")
    file_set = hashlib.sha256()
    if stats is not None:
        stats["run_files"] = len(paths)
        stats["runs_without_legitimate_task"] = 0
    found: dict[str, Candidate] = {}
    for path in paths:
        if (
            path.is_symlink()
            or not path.resolve().is_relative_to(root.resolve())
            or not path.is_file()
            or path.stat().st_size > 4 * 1024 * 1024
        ):
            raise ValueError(f"AgentDojo run missing, linked or oversized: {path}")
        file_set.update(
            os.fsencode(str(path.relative_to(root))) + b"\0" + _sha256(path).encode() + b"\n"
        )
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
                stats["runs_without_legitimate_task"] = (
                    int(stats["runs_without_legitimate_task"]) + 1
                )
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
        stats["file_set_sha256"] = file_set.hexdigest()
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
