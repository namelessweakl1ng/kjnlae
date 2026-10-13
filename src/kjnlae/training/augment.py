"""Deterministic TRAIN-only source balancing for public benign examples."""

import argparse
import random
from pathlib import Path

from kjnlae.schemas import Source
from kjnlae.training.dataset import TrainingExample

SOURCE_SCHEDULE: tuple[Source, ...] = (
    ("retrieved_document",) * 100
    + ("webpage",) * 30
    + ("email",) * 25
    + ("tool_response",) * 25
    + ("attachment",) * 20
)


def augment_benign_sources(
    train_path: Path, output_path: Path, *, count: int = 200, seed: int = 43
) -> int:
    """Relabel only TRAIN provenance context; preserve text, label and family."""
    rows = [
        TrainingExample.model_validate_json(line) for line in train_path.read_text().splitlines()
    ]
    if not rows or any(row.split != "TRAIN" for row in rows):
        raise ValueError("Only a complete TRAIN partition may be augmented")
    if not 1 <= count <= len(SOURCE_SCHEDULE):
        raise ValueError("Augmentation count must be within the reviewed source schedule")
    pool = [
        row
        for row in rows
        if row.label == 0 and row.source == "user" and row.provenance_id == "deepset-4f61ecb"
    ]
    if count > len(pool):
        raise ValueError("Not enough public benign TRAIN examples for augmentation")
    selected = random.Random(seed).sample(pool, count)
    augmented = [
        row.model_copy(update={"id": f"{row.id}-source-v3", "source": source})
        for row, source in zip(selected, SOURCE_SCHEDULE, strict=False)
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(row.model_dump_json() + "\n" for row in augmented))
    return len(augmented)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--seed", type=int, default=43)
    args = parser.parse_args()
    print(augment_benign_sources(args.train, args.output, count=args.count, seed=args.seed))
