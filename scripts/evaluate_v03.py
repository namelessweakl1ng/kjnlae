"""Development selection and one-time frozen comparison for v0.3 DistilBERT."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from kjnlae.classifiers.artifacts import PUBLIC_MODEL_MANIFEST_SHA256, verify_artifact
from kjnlae.evaluation.comparison import summarize_scored_cases
from kjnlae.evaluation.model import _score_rows
from kjnlae.evaluation.operating_point import select_operating_point

FINAL_SHA256 = "b2bb9762a8fbe574071fd6836e484f4e185f208c1b1799491aa0a628c9efd699"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _score(model: Path, rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    scores, latencies = _score_rows(model, rows)
    result = summarize_scored_cases(rows, scores, threshold=threshold)
    result["mean_forward_seconds"] = sum(latencies) / len(latencies)
    result["scores"] = [
        {"id": row["id"], "label": row["label"], "score": score}
        for row, score in zip(rows, scores, strict=True)
    ]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("development", "final"))
    parser.add_argument("--control", required=True, type=Path)
    parser.add_argument("--fit", required=True, type=Path)
    parser.add_argument("--prepared", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    control = verify_artifact(args.control, PUBLIC_MODEL_MANIFEST_SHA256)
    fit_report_path = args.fit / "fit-report.json"
    fit_report = json.loads(fit_report_path.read_text())
    if fit_report.get("status") != "COMPLETE" or fit_report.get("steps", 0) <= 0:
        raise ValueError("A complete, genuine fine-tuning run is required")
    candidate = args.fit / "best"
    candidate_hash = _sha(candidate / "model.safetensors")
    if candidate_hash != fit_report.get("best_weight_sha256"):
        raise ValueError("Candidate weights do not match the completed fit report")
    args.output.mkdir(parents=True, exist_ok=True)
    selection_path = args.output / "selection.json"

    if args.phase == "development":
        if selection_path.exists():
            raise FileExistsError("Development selection is already sealed")
        cal_path = args.prepared / "calibration.jsonl"
        val_path = args.prepared / "validation.jsonl"
        calibration, validation = _rows(cal_path), _rows(val_path)
        if not calibration or not validation or any(
            row["split"] != "CALIBRATION" for row in calibration
        ) or any(row["split"] != "VALIDATION" for row in validation):
            raise ValueError("Malformed development partitions")
        candidate_scores, _ = _score_rows(candidate, calibration)
        truth = [row["label"] for row in calibration]
        try:
            point = select_operating_point(truth, candidate_scores, max_fpr=0.1, min_recall=0.9)
            threshold: float | None = point.threshold
            status = "SELECTED"
        except ValueError:
            threshold = None
            status = "NO_OPERATING_POINT"
        report: dict[str, Any] = {
            "status": status,
            "candidate_weight_sha256": candidate_hash,
            "control_manifest_sha256": control.sha256,
            "fit_report_sha256": _sha(fit_report_path),
            "validation_sha256": _sha(val_path),
            "calibration_sha256": _sha(cal_path),
            "frozen_final_sha256": FINAL_SHA256,
            "threshold": threshold,
            "objective": {"max_calibration_fpr": 0.1, "min_calibration_recall": 0.9},
            "calibration_candidate_scores": [
                {"id": row["id"], "label": row["label"], "score": score}
                for row, score in zip(calibration, candidate_scores, strict=True)
            ],
            "control_calibration": _score(args.control, calibration, control.threshold),
            "control_validation": _score(args.control, validation, control.threshold),
        }
        if threshold is not None:
            report["candidate_calibration"] = summarize_scored_cases(
                calibration, candidate_scores, threshold=threshold
            )
            report["candidate_validation"] = _score(candidate, validation, threshold)
        selection_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps({k: report[k] for k in ("status", "threshold", "objective")}, indent=2))
        return

    final_path = Path(__file__).resolve().parents[1] / "datasets/fixtures/v0.3-frozen-final.jsonl"
    final_report = args.output / "final-comparison.json"
    if final_report.exists():
        raise FileExistsError("Frozen final set was already evaluated in this output directory")
    selection = json.loads(selection_path.read_text())
    if (
        selection.get("status") != "SELECTED"
        or selection.get("candidate_weight_sha256") != candidate_hash
        or selection.get("calibration_sha256") != _sha(args.prepared / "calibration.jsonl")
        or selection.get("validation_sha256") != _sha(args.prepared / "validation.jsonl")
        or _sha(final_path) != FINAL_SHA256
    ):
        raise ValueError("Frozen selection, candidate, or test identity changed")
    final = _rows(final_path)
    if len(final) != 120 or sum(row["label"] == 0 for row in final) != 80:
        raise ValueError("Unexpected frozen test composition")
    result = {
        "status": "MEASURED",
        "frozen_final_sha256": FINAL_SHA256,
        "candidate_weight_sha256": candidate_hash,
        "selection_sha256": _sha(selection_path),
        "control": _score(args.control, final, control.threshold),
        "candidate": _score(candidate, final, float(selection["threshold"])),
    }
    final_report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    metrics = {key: result[key]["metrics"] for key in ("control", "candidate")}
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
