"""Pinned import adapters for external diagnostic benchmarks."""

import csv
import hashlib
import io
import re
from pathlib import Path
from typing import Literal

from kjnlae.evaluation.release_cases import EvaluationCase

S_LABS_REVISION = "002a9dd18514abd021869823d6b0429b38606d99"
S_LABS_TEST_SHA256 = "4c7a9f0fff2bf7d3f6d3e7b84863a8f5d6c48c70c3ac7fe874917074c8f27853"


def import_s_labs_test(path: Path, *, expected_sha256: str) -> list[EvaluationCase]:
    """Map the MIT-licensed test CSV to unreviewed direct-user diagnostics.

    The adapter cannot establish label validity, source diversity, or real-world
    representativeness. The caller pins the original CSV digest before scoring.
    """
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Expected SHA-256 must be a lowercase 64-character hex digest")
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("External CSV missing, linked, or exceeds 16 MiB")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("External CSV SHA-256 differs from pinned source")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""))
    if reader.fieldnames != ["text", "label"]:
        raise ValueError("External CSV needs exactly text,label columns")
    rows: list[EvaluationCase] = []
    families: set[str] = set()
    for index, record in enumerate(reader):
        if record["label"] == "0":
            label: Literal[0, 1] = 0
        elif record["label"] == "1":
            label = 1
        else:
            raise ValueError(f"External row {index}: label must be 0 or 1")
        text = record["text"]
        if not isinstance(text, str):
            raise ValueError(f"External row {index}: missing text")
        family = hashlib.sha256(text.casefold().encode("utf-8")).hexdigest()
        if family in families:
            raise ValueError("Duplicate external content family")
        families.add(family)
        rows.append(
            EvaluationCase(
                id=f"s-labs-test-{index:05d}",
                family_id=family,
                text=text,
                label=label,
                source="user",
                category="external_unreviewed",
                provenance=f"S-Labs/prompt-injection-dataset@{S_LABS_REVISION}",
            )
        )
        if len(rows) > 10000:
            raise ValueError("External CSV exceeds 10000 rows")
    if not rows:
        raise ValueError("External CSV is empty")
    return rows
