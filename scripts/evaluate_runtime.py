"""Measure complete, real ONNX Guard scans on a labeled JSONL fixture."""

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

from kjnlae import Guard
from kjnlae.classifiers.artifacts import verify_onnx_artifact
from kjnlae.evaluation.comparison import summarize_scored_cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--hash", required=True)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    artifact = verify_onnx_artifact(args.model, args.hash)
    rows: list[dict[str, Any]] = [
        json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line
    ]
    if not rows or any(row.get("label") not in (0, 1) for row in rows):
        raise ValueError("Labeled JSONL examples required")
    scores: list[float] = []
    latencies: list[float] = []
    windows: list[dict[str, Any]] = []
    with Guard(model_dir=str(args.model), model_hash=args.hash) as guard:
        for row in rows:
            result = guard.scan(row["text"], source=row["source"])
            if (
                not result.inspection_complete
                or result.model_status != "AVAILABLE"
                or result.model_score is None
                or result.model_hash != artifact.sha256
            ):
                raise RuntimeError(f"Incomplete runtime inspection: {row['id']}")
            scores.append(result.model_score)
            latencies.append(result.latency_ms)
            windows.append(
                {
                    "id": row["id"],
                    "count": len(result.windows),
                    "last_source_end": max((window.end for window in result.windows), default=0),
                }
            )
    summary = summarize_scored_cases(rows, scores, threshold=artifact.threshold)
    summary.update(
        {
            "model_manifest_sha256": artifact.sha256,
            "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
            "complete_count": len(scores),
            "mean_scan_ms": statistics.mean(latencies),
            "warm_mean_scan_ms": statistics.mean(latencies[1:]) if len(latencies) > 1 else None,
            "windows": windows,
            "scores": [
                {"id": row["id"], "score": score} for row, score in zip(rows, scores, strict=True)
            ],
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "metrics": summary["metrics"],
                "complete_count": len(scores),
                "mean_scan_ms": summary["mean_scan_ms"],
                "warm_mean_scan_ms": summary["warm_mean_scan_ms"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
