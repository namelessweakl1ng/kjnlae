"""Validated, provenance-tracked partitions for local fine-tuning."""

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from kjnlae.schemas import Source

Split = Literal["TRAIN", "VALIDATION", "CALIBRATION", "HELD_OUT_TEST"]
SPLITS: tuple[Split, ...] = ("TRAIN", "VALIDATION", "CALIBRATION", "HELD_OUT_TEST")
PROVENANCE = {
    "original": {"license": "MIT", "origin": "kjnlae fictional authored fixtures"},
    "deepset-4f61ecb": {
        "license": (
            "Apache-2.0 / CC-BY-4.0 metadata discrepancy; both attribution obligations observed"
        ),
        "origin": "deepset/prompt-injections",
        "revision": "4f61ecb038e9c3fb77e21034b22511b523772cdd",
    },
    "bipia-a004b69": {
        "license": (
            "MIT for Microsoft-authored attack prompts; repository NOTICE retained separately"
        ),
        "origin": "microsoft/BIPIA benchmark/text_attack_train.json",
        "revision": "a004b69ec0dd446e0afd461d98cb5e96e120a5d0",
    },
}

DEEPSET_HASHES = {
    "TRAIN": "2e10bc7ab30f542c97e4e83e2a5683000b5057d25ec10908784c631d44124c04",
    "HELD_OUT_TEST": "39ac797cabc157eeed58435a08593b2952bb6cb16fc394a2d383f447cc7b246e",
}

_BIPIA_ACTIVE_CATEGORIES = frozenset(
    {
        "Alphanumeric Substitution",
        "Homophonic Substitution",
        "Misspelling Intentionally",
        "Anagramming",
        "Space Removal & Grouping",
        "Instruction",
        "Social Interaction",
        "Persuasion",
        "Clickbait",
        "Malware Distribution",
    }
)


class TrainingExample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=32768)
    source: Source
    label: Literal[0, 1]
    split: Split
    family_id: str = Field(min_length=1)
    provenance_id: str


@dataclass(frozen=True)
class SplitManifest:
    seed: int
    counts: dict[str, int]
    sha256: dict[str, str]
    source_sha256: dict[str, str]


def import_bipia_attacks(source: Path, target: Path, repository_commit: str) -> int:
    """Import only active injected TRAIN prompts, never BIPIA context or test data."""
    if repository_commit != PROVENANCE["bipia-a004b69"]["revision"]:
        raise ValueError("BIPIA revision differs from reviewed source")
    data = json.loads(source.read_text())
    if not isinstance(data, dict):
        raise ValueError("BIPIA attack file must contain category lists")
    rows: list[str] = []
    for category in sorted(_BIPIA_ACTIVE_CATEGORIES):
        prompts = data.get(category, [])
        if not isinstance(prompts, list):
            raise ValueError("Malformed BIPIA category")
        for index, prompt in enumerate(prompts):
            if not isinstance(prompt, str):
                raise ValueError("Malformed BIPIA prompt")
            row = TrainingExample(
                id=f"bipia-{category.lower().replace(' ', '-')}-{index}",
                text=prompt,
                source="retrieved_document",
                label=1,
                split="TRAIN",
                family_id=f"bipia-{category.lower().replace(' ', '-')}-{index}",
                provenance_id="bipia-a004b69",
            )
            rows.append(row.model_dump_json() + "\n")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(rows))
    return len(rows)


def import_deepset(source: Path, target: Path, split: Split) -> int:
    """Import pinned public examples while honoring both recorded license notices."""
    if (
        split not in DEEPSET_HASHES
        or hashlib.sha256(source.read_bytes()).hexdigest() != (DEEPSET_HASHES[split])
    ):
        raise ValueError("Deepset source SHA256 differs from reviewed pinned parquet")
    import pyarrow.parquet as parquet

    rows: list[str] = []
    for index, item in enumerate(parquet.read_table(source).to_pylist()):
        row = TrainingExample(
            id=f"deepset-{split.lower()}-{index:04d}",
            text=item["text"],
            source="user",
            label=item["label"],
            split=split,
            family_id=f"deepset-{split.lower()}-{index:04d}",
            provenance_id="deepset-4f61ecb",
        )
        rows.append(row.model_dump_json() + "\n")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(rows))
    return len(rows)


def _normalized(text: str) -> str:
    return re.sub(r"[^\w]+", "", unicodedata.normalize("NFKC", text).casefold())


def prepare_dataset(sources: list[Path], output_dir: Path, seed: int) -> SplitManifest:
    rows: dict[str, list[TrainingExample]] = {split: [] for split in SPLITS}
    families: dict[str, str] = {}
    seen_ids: set[str] = set()
    normalized: dict[str, str] = {}
    source_hashes: dict[str, str] = {}
    for path in sources:
        raw = path.read_bytes()
        source_hashes[path.name] = hashlib.sha256(raw).hexdigest()
        for line in raw.splitlines():
            if not line:
                continue
            row = TrainingExample.model_validate_json(line)
            if row.provenance_id not in PROVENANCE:
                raise ValueError(f"Unreviewed provenance: {row.provenance_id}")
            if row.id in seen_ids:
                raise ValueError("Duplicate example id")
            seen_ids.add(row.id)
            if row.family_id in families and families[row.family_id] != row.split:
                raise ValueError("Family leakage across partitions")
            families[row.family_id] = row.split
            key = _normalized(row.text)
            if key in normalized and normalized[key] != row.split:
                raise ValueError("Normalized text leakage across partitions")
            for other, split in normalized.items():
                if (
                    split != row.split
                    and max(len(key), len(other)) <= 2048
                    and abs(len(key) - len(other)) <= max(len(key), len(other)) * 0.04
                    and SequenceMatcher(None, key, other).ratio() >= 0.96
                ):
                    raise ValueError("Near-duplicate leakage across partitions")
            normalized[key] = row.split
            rows[row.split].append(row)
    if not rows["TRAIN"]:
        raise ValueError("TRAIN partition cannot be empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    split_hashes: dict[str, str] = {}
    for split in SPLITS:
        content = "".join(row.model_dump_json() + "\n" for row in rows[split]).encode()
        split_hashes[split] = hashlib.sha256(content).hexdigest()
        (output_dir / f"{split.lower()}.jsonl").write_bytes(content)
    manifest = SplitManifest(seed, {s: len(rows[s]) for s in SPLITS}, split_hashes, source_hashes)
    (output_dir / "manifest.json").write_text(
        json.dumps({**manifest.__dict__, "provenance": PROVENANCE}, indent=2, sort_keys=True) + "\n"
    )
    return manifest
