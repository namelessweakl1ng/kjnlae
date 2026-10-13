"""Pure classification metrics; scores are model-specific, not attack-success probabilities."""

import hashlib
import json
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from kjnlae.classifiers.artifacts import BASE_REVISION, verify_artifact
from kjnlae.classifiers.local import window_ranges


def classification_metrics(
    truth: Sequence[int], predicted: Sequence[int]
) -> dict[str, float | int]:
    if len(truth) != len(predicted) or not truth:
        raise ValueError("Aligned, nonempty labels required")
    if set(truth) - {0, 1} or set(predicted) - {0, 1}:
        raise ValueError("Binary labels required")
    tp = sum(y == p == 1 for y, p in zip(truth, predicted, strict=True))
    tn = sum(y == p == 0 for y, p in zip(truth, predicted, strict=True))
    fp = sum(y == 0 and p == 1 for y, p in zip(truth, predicted, strict=True))
    fn = sum(y == 1 and p == 0 for y, p in zip(truth, predicted, strict=True))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "false_positive_rate": fp / (fp + tn) if fp + tn else 0.0,
        "false_negative_rate": fn / (fn + tp) if fn + tp else 0.0,
    }


def calibrate_threshold(truth: Sequence[int], scores: Sequence[float]) -> float:
    if len(truth) != len(scores) or not truth or set(truth) != {0, 1}:
        raise ValueError("CALIBRATION requires both classes and aligned scores")
    if any(not 0 <= score <= 1 for score in scores):
        raise ValueError("Scores must lie in [0, 1]")
    candidates = sorted(set(scores) | {0.5})
    return max(
        candidates,
        key=lambda threshold: (
            classification_metrics(truth, [int(s >= threshold) for s in scores])["f1"],
            -classification_metrics(truth, [int(s >= threshold) for s in scores])[
                "false_positive_rate"
            ],
            -abs(threshold - 0.5),
        ),
    )


def validate_evaluation_splits(
    calibration: Path, held_out: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    partitions = []
    for path, expected in ((calibration, "CALIBRATION"), (held_out, "HELD_OUT_TEST")):
        rows = [json.loads(line) for line in path.read_text().splitlines() if line]
        if not rows or any(row.get("split") != expected for row in rows):
            raise ValueError(f"{expected} partition missing or malformed")
        partitions.append(rows)
    if {r["id"] for r in partitions[0]} & {r["id"] for r in partitions[1]}:
        raise ValueError("Calibration/test leakage")
    return partitions[0], partitions[1]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _score_rows(model_dir: Path, rows: list[dict[str, Any]]) -> tuple[list[float], list[float]]:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer  # type: ignore[attr-defined]

    torch.set_num_threads(4)
    tokenizer = AutoTokenizer.from_pretrained(
        model_dir, local_files_only=True, trust_remote_code=False
    )
    model = AutoModelForSequenceClassification.from_pretrained(
        model_dir, local_files_only=True, trust_remote_code=False, use_safetensors=True
    ).eval()
    scores: list[float] = []
    latencies: list[float] = []
    for row in rows:
        prefix = tokenizer.encode(f"Source: {row['source']}\nContent:\n", add_special_tokens=False)
        ids = tokenizer.encode(row["text"], add_special_tokens=False)
        width = 128 - tokenizer.num_special_tokens_to_add(pair=False) - len(prefix)
        ranges = window_ranges(len(ids), width, 32)
        if len(ranges) > 128:
            raise ValueError("Evaluation sample exceeds complete window budget")
        started = time.monotonic()
        window_scores: list[float] = []
        with torch.inference_mode():
            for start, end in ranges:
                encoded = tokenizer.prepare_for_model(
                    prefix + ids[start:end], add_special_tokens=True
                )
                batch = tokenizer.pad([encoded], padding=True, return_tensors="pt")
                probability = torch.softmax(model(**batch).logits, dim=-1)[0, 1]
                window_scores.append(float(probability))
        latencies.append(time.monotonic() - started)
        scores.append(max(window_scores))
    return scores, latencies


def evaluate_and_promote(fit_dir: Path, prepared_dir: Path) -> dict[str, Any]:
    fit_report = json.loads((fit_dir / "fit-report.json").read_text())
    if fit_report.get("status") != "COMPLETE" or fit_report.get("steps", 0) <= 0:
        raise ValueError("Complete genuine training report required")
    calibration_path = prepared_dir / "calibration.jsonl"
    held_out_path = prepared_dir / "held_out_test.jsonl"
    calibration, held_out = validate_evaluation_splits(calibration_path, held_out_path)
    truth_cal = [int(r["label"]) for r in calibration]
    truth_test = [int(r["label"]) for r in held_out]
    outcomes: dict[str, Any] = {}
    trained_threshold = 0.5
    for name, model_dir in (
        ("untrained_head", fit_dir / "initial-control"),
        ("fine_tuned", fit_dir / "best"),
    ):
        cal_scores, cal_latencies = _score_rows(model_dir, calibration)
        threshold = calibrate_threshold(truth_cal, cal_scores)
        if name == "fine_tuned":
            trained_threshold = threshold
        test_scores, test_latencies = _score_rows(model_dir, held_out)
        metrics = classification_metrics(truth_test, [int(s >= threshold) for s in test_scores])
        outcomes[name] = {
            "threshold": threshold,
            "calibration_metrics": classification_metrics(
                truth_cal, [int(s >= threshold) for s in cal_scores]
            ),
            "held_out_metrics": metrics,
            "test_scores": [
                {"id": r["id"], "label": r["label"], "score": score}
                for r, score in zip(held_out, test_scores, strict=True)
            ],
            "mean_test_inference_seconds": sum(test_latencies) / len(test_latencies),
            "mean_calibration_inference_seconds": sum(cal_latencies) / len(cal_latencies),
            "weight_sha256": _sha(model_dir / "model.safetensors"),
        }
    report = {
        "status": "MEASURED",
        "training_status": fit_report["status"],
        "data_counts": {
            "TRAIN": fit_report["train_count"],
            "VALIDATION": fit_report["validation_count"],
            "CALIBRATION": len(calibration),
            "HELD_OUT_TEST": len(held_out),
        },
        "split_sha256": {
            "CALIBRATION": _sha(calibration_path),
            "HELD_OUT_TEST": _sha(held_out_path),
        },
        "base_revision": BASE_REVISION,
        "control_note": (
            "Random, seeded classifier head on approved pretrained encoder; "
            "not an injection detector"
        ),
        "outcomes": outcomes,
    }
    report_path = fit_dir / "evaluation-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    best = fit_dir / "best"
    files = {p.name: _sha(p) for p in best.iterdir() if p.is_file() and p.name != "manifest.json"}
    manifest = {
        "artifact_version": "kjnlae-v0.2-local-1",
        "base_revision": BASE_REVISION,
        "trained_steps": fit_report["steps"],
        "best_epoch": fit_report["best_epoch"],
        "seed": fit_report["config"]["seed"],
        "approved": True,
        "threshold": trained_threshold,
        "label_mapping": {"0": "NON_INJECTION", "1": "INJECTION"},
        "train_sha256": fit_report["train_sha256"],
        "validation_sha256": fit_report["validation_sha256"],
        "calibration_sha256": _sha(calibration_path),
        "held_out_sha256": _sha(held_out_path),
        "evaluation_report_sha256": _sha(report_path),
        "files": files,
    }
    manifest_path = best / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    verified = verify_artifact(best, _sha(manifest_path))
    report["artifact_path"] = str(verified.path.resolve())
    report["manifest_sha256"] = verified.sha256
    return report
