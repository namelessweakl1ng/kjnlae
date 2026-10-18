"""Compare verified PyTorch checkpoint and ONNX derivative on identical frozen rows."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from kjnlae.classifiers.artifacts import (
    verify_artifact,
    verify_onnx_artifact,
)
from kjnlae.classifiers.local import LocalClassifier, LocalModelConfig, window_ranges
from kjnlae.detection.preprocessing import prepare_views
from kjnlae.evaluation.model import classification_metrics
from kjnlae.training.dataset import DEEPSET_HASHES


def load_rows(path: Path) -> list[dict[str, Any]]:
    """Read authored fixtures or the exact pinned Deepset held-out parquet."""
    if path.suffix == ".parquet":
        if hashlib.sha256(path.read_bytes()).hexdigest() != DEEPSET_HASHES["HELD_OUT_TEST"]:
            raise ValueError("Deepset source SHA256 differs from reviewed pinned parquet")
        import pyarrow.parquet as parquet

        source_rows = parquet.read_table(path).to_pylist()
        return [
            {
                "id": f"deepset-{index}",
                "source": "user",
                "text": row["text"],
                "label": int(row["label"]),
            }
            for index, row in enumerate(source_rows)
        ]
    if path.suffix == ".jsonl":
        source_rows = [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line
        ]
    elif path.suffix == ".json":
        source_rows = json.loads(path.read_text(encoding="utf-8"))
    else:
        raise ValueError("Expected JSON, JSONL or pinned Deepset parquet")
    if not isinstance(source_rows, list) or not source_rows:
        raise ValueError("Dataset must contain a nonempty list")
    return [
        {
            "id": str(row["id"]),
            "source": row["source"],
            "text": row["text"],
            "label": int(row.get("label", row.get("attack"))),
        }
        for row in source_rows
    ]


def compare(
    torch_dir: Path, onnx_dir: Path, onnx_hash: str, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Require every view/window and offset to agree before reporting metrics."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    artifact = verify_onnx_artifact(onnx_dir, onnx_hash)
    derivative = json.loads((artifact.path / "manifest.json").read_text())
    verify_artifact(torch_dir, derivative["source_manifest_sha256"])
    torch.set_num_threads(4)
    tokenizer = AutoTokenizer.from_pretrained(
        torch_dir, local_files_only=True, use_fast=True, trust_remote_code=False
    )
    model = AutoModelForSequenceClassification.from_pretrained(
        torch_dir, local_files_only=True, use_safetensors=True, trust_remote_code=False
    ).eval()
    classifier = LocalClassifier(LocalModelConfig(onnx_dir, onnx_hash))
    reference_scores: list[float] = []
    optimized_scores: list[float] = []
    maximum_window_difference = 0.0
    window_count = 0
    try:
        for row in rows:
            prepared = prepare_views(row["text"])
            if not prepared.complete:
                raise ValueError(f"Incomplete preprocessing for {row['id']}")
            inference = classifier.classify_views(prepared.views, row["source"])
            if inference.status != "AVAILABLE" or not inference.inspection_complete:
                raise ValueError(f"ONNX incomplete for {row['id']}: {inference.reason}")
            prefix = tokenizer.encode(
                f"Source: {row['source']}\nContent:\n", add_special_tokens=False
            )
            width = 128 - tokenizer.num_special_tokens_to_add(pair=False) - len(prefix)
            old_windows: list[tuple[str, tuple[int, int], float]] = []
            with torch.inference_mode():
                for view in prepared.views:
                    encoded = tokenizer(
                        view.text, add_special_tokens=False, return_offsets_mapping=True
                    )
                    ids, offsets = encoded["input_ids"], encoded["offset_mapping"]
                    for start, end in window_ranges(len(ids), width, 32):
                        selected = ids[start:end]
                        if selected:
                            span = (
                                view.mapping[offsets[start][0]][0],
                                view.mapping[offsets[end - 1][1] - 1][1],
                            )
                        else:
                            span = (0, 0)
                        batch = tokenizer.pad(
                            [
                                tokenizer.prepare_for_model(
                                    prefix + selected, add_special_tokens=True
                                )
                            ],
                            padding=True,
                            return_tensors="pt",
                        )
                        score = float(torch.softmax(model(**batch).logits, dim=-1)[0, 1])
                        old_windows.append((view.name, span, score))
            if len(old_windows) != len(inference.windows):
                raise ValueError(f"Window count changed for {row['id']}")
            for old, new in zip(old_windows, inference.windows, strict=True):
                if (old[0], old[1]) != (new.view, new.source_span) or new.score is None:
                    raise ValueError(f"Window offsets changed for {row['id']}")
                maximum_window_difference = max(maximum_window_difference, abs(old[2] - new.score))
            window_count += len(old_windows)
            reference_scores.append(max(value[2] for value in old_windows))
            if inference.score is None:
                raise ValueError(f"ONNX score missing for {row['id']}")
            optimized_scores.append(inference.score)
    finally:
        classifier.close()
    truth = [row["label"] for row in rows]
    old_pred = [int(score >= artifact.threshold) for score in reference_scores]
    new_pred = [int(score >= artifact.threshold) for score in optimized_scores]
    return {
        "dataset_sha256": None,
        "samples": len(rows),
        "windows": window_count,
        "threshold": artifact.threshold,
        "max_abs_window_score_difference": maximum_window_difference,
        "max_abs_aggregate_score_difference": max(
            abs(a - b) for a, b in zip(reference_scores, optimized_scores, strict=True)
        ),
        "decision_flips": sum(a != b for a, b in zip(old_pred, new_pred, strict=True)),
        "torch_metrics": classification_metrics(truth, old_pred),
        "onnx_metrics": classification_metrics(truth, new_pred),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--torch", type=Path, required=True, help="Verified original checkpoint")
    parser.add_argument("--onnx", type=Path, required=True, help="Verified derived artifact")
    parser.add_argument("--hash", required=True, help="Trusted ONNX manifest SHA-256")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = load_rows(args.dataset)
    report = compare(args.torch, args.onnx, args.hash, rows)
    report["dataset_sha256"] = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
