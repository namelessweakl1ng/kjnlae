"""Validate sealed, independently sourced classifier evaluation cases."""

import hashlib
import re
import unicodedata
from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from kjnlae.schemas import Source


class EvaluationCase(BaseModel):
    """One labeled content family; labels mean injection, not authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(min_length=1, max_length=128)
    family_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=32768)
    label: Literal[0, 1]
    source: Source
    category: str = Field(min_length=1, max_length=128)
    provenance: str = Field(min_length=1, max_length=256)

    @field_validator("label", mode="before")
    @classmethod
    def reject_boolean_label(cls, value: object) -> object:
        if type(value) is bool:
            raise ValueError("label must be the integer 0 or 1")
        return value


def _normalized(text: str) -> str:
    """Use Unicode-stable comparison only for leakage checks, never detection."""
    return re.sub(r"[^\w]+", "", unicodedata.normalize("NFKC", text).casefold())


def load_cases(path: Path, expected_sha256: str) -> list[EvaluationCase]:
    """Load a bounded frozen JSONL file only when its trusted SHA-256 matches."""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Expected SHA-256 must be a lowercase 64-character hex digest")
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Evaluation file missing, linked, or exceeds 32 MiB")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Evaluation SHA-256 differs from frozen manifest")
    if not raw.endswith(b"\n"):
        raise ValueError("Evaluation JSONL must end with LF")
    rows = [EvaluationCase.model_validate_json(line) for line in raw.splitlines() if line]
    if not 1 <= len(rows) <= 10000:
        raise ValueError("Evaluation must contain 1..10000 cases")
    if len({row.id for row in rows}) != len(rows):
        raise ValueError("Duplicate evaluation id")
    if len({row.family_id for row in rows}) != len(rows):
        raise ValueError("Duplicate evaluation family")
    if len({_normalized(row.text) for row in rows}) != len(rows):
        raise ValueError("Duplicate normalized evaluation text")
    return rows


def check_partition_leakage(
    train: Sequence[Mapping[str, Any]], final: Sequence[EvaluationCase]
) -> None:
    """Reject family, normalized-text and high-similarity development overlap."""
    train_items = [
        (str(row["id"]), str(row["family_id"]), _normalized(str(row["text"]))) for row in train
    ]
    families = {family for _, family, _ in train_items}
    normalized = {text for _, _, text in train_items}
    for case in final:
        if case.family_id in families:
            raise ValueError(f"Final family overlaps development: {case.id}")
        text = _normalized(case.text)
        if text in normalized:
            raise ValueError(f"Normalized text overlaps development: {case.id}")
        for identifier, _, candidate in train_items:
            longest = max(len(text), len(candidate))
            if longest < 20 or abs(len(text) - len(candidate)) > longest * 0.20:
                continue
            matcher = SequenceMatcher(None, text, candidate, autojunk=False)
            if matcher.quick_ratio() >= 0.85 and matcher.ratio() >= 0.85:
                raise ValueError(f"Near-duplicate final/development text: {case.id} / {identifier}")
