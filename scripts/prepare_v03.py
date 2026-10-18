"""Build the v0.3 development partitions from pinned public and authored data.

The frozen final fixture is checked for leakage but never copied into a
training, validation, or calibration partition.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from kjnlae.training.dataset import (
    TrainingExample,
    import_bipia_attacks,
    import_deepset,
    prepare_dataset,
)
from kjnlae.training.v03_data import authored_rows, reject_frozen_overlap


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deepset-train", required=True, type=Path)
    parser.add_argument("--bipia-train", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    work = args.output
    inputs = work / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)

    original = [
        TrainingExample.model_validate_json(line)
        for line in (root / "datasets/fixtures/v2_seed.jsonl").read_text().splitlines()
        if line
    ]
    original_train = [row for row in original if row.split == "TRAIN"]
    (inputs / "v2-original-train-only.jsonl").write_text(
        "".join(row.model_dump_json() + "\n" for row in original_train)
    )
    authored = authored_rows()
    (inputs / "v03-authored.jsonl").write_text(
        "".join(row.model_dump_json() + "\n" for row in authored)
    )
    final = [
        json.loads(line)
        for line in (root / "datasets/fixtures/v0.3-frozen-final.jsonl").read_text().splitlines()
    ]
    reject_frozen_overlap(
        authored
        + original_train
        + [
            TrainingExample.model_validate_json(line)
            for line in (root / "datasets/fixtures/v0.2-benign-train.jsonl")
            .read_text()
            .splitlines()
        ],
        final,
    )
    import_deepset(args.deepset_train, inputs / "deepset-train.jsonl", "TRAIN")
    import_bipia_attacks(
        args.bipia_train,
        inputs / "bipia-train.jsonl",
        "a004b69ec0dd446e0afd461d98cb5e96e120a5d0",
    )
    public = [
        TrainingExample.model_validate_json(line)
        for name in ("deepset-train.jsonl", "bipia-train.jsonl")
        for line in (inputs / name).read_text().splitlines()
    ]
    reject_frozen_overlap(public, final)
    sources = [
        inputs / "v2-original-train-only.jsonl",
        root / "datasets/fixtures/v0.2-benign-train.jsonl",
        inputs / "v03-authored.jsonl",
        inputs / "deepset-train.jsonl",
        inputs / "bipia-train.jsonl",
    ]
    manifest = prepare_dataset(sources, work / "prepared", seed=73)
    rows = [
        TrainingExample.model_validate_json(line)
        for path in sources
        for line in path.read_text().splitlines()
    ]
    summary = {
        "split_counts": manifest.counts,
        "split_sha256": manifest.sha256,
        "source_sha256": manifest.source_sha256,
        "label_split": {
            split: dict(Counter(row.label for row in rows if row.split == split))
            for split in ("TRAIN", "VALIDATION", "CALIBRATION")
        },
        "source_label": {
            split: {
                source: dict(
                    Counter(
                        row.label for row in rows if row.split == split and row.source == source
                    )
                )
                for source in sorted({row.source for row in rows if row.split == split})
            }
            for split in ("TRAIN", "VALIDATION", "CALIBRATION")
        },
    }
    (work / "data-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
