"""Compare fixed v0.3 candidate with v0.2 on previously seen research sets."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from kjnlae.classifiers.artifacts import PUBLIC_MODEL_MANIFEST_SHA256, verify_artifact
from kjnlae.evaluation.comparison import summarize_scored_cases
from kjnlae.evaluation.model import _score_rows
from kjnlae.training.dataset import DEEPSET_HASHES


def _score(model: Path, rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    scores, latency = _score_rows(model, rows)
    summary = summarize_scored_cases(rows, scores, threshold=threshold)
    summary["mean_forward_seconds"] = sum(latency) / len(latency)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--deepset-test", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    control = verify_artifact(args.control, PUBLIC_MODEL_MANIFEST_SHA256)
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    candidate_hash = hashlib.sha256((args.candidate / "model.safetensors").read_bytes()).hexdigest()
    if selection.get("status") != "SELECTED" or candidate_hash != selection.get(
        "candidate_weight_sha256"
    ):
        raise ValueError("Candidate does not match sealed development selection")
    deepset_hash = hashlib.sha256(args.deepset_test.read_bytes()).hexdigest()
    if deepset_hash != DEEPSET_HASHES["HELD_OUT_TEST"]:
        raise ValueError("Deepset test file hash mismatch")
    import pyarrow.parquet as parquet

    deepset = [
        {
            "id": f"deepset-test-{i:03d}",
            "text": row["text"],
            "label": row["label"],
            "source": "user",
            "category": "deepset-contextual-label",
        }
        for i, row in enumerate(parquet.read_table(args.deepset_test).to_pylist())
    ]
    paths = {
        "original_30": root / "src/kjnlae/evaluation/fixtures.json",
        "independent_50": root / "datasets/fixtures/v0.2-independent-eval.json",
    }
    datasets: dict[str, list[dict[str, Any]]] = {"deepset_116": deepset}
    for name, path in paths.items():
        rows = json.loads(path.read_text(encoding="utf-8"))
        datasets[name] = [{**row, "label": int(row["attack"])} for row in rows]
    report: dict[str, Any] = {
        "candidate_weight_sha256": candidate_hash,
        "control_manifest_sha256": control.sha256,
        "selection_sha256": hashlib.sha256(args.selection.read_bytes()).hexdigest(),
        "sets": {},
    }
    for name, rows in datasets.items():
        report["sets"][name] = {
            "count": len(rows),
            "control": _score(args.control, rows, control.threshold),
            "control_recalibrated": _score(
                args.control, rows, float(selection["control_recalibrated_threshold"])
            ),
            "candidate": _score(args.candidate, rows, float(selection["threshold"])),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                name: {
                    model: item[model]["metrics"]
                    for model in ("control", "control_recalibrated", "candidate")
                }
                for name, item in report["sets"].items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
