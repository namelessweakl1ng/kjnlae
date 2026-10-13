"""Observed fixture metrics for one fine-tuned detector and independent controls."""

import hashlib
import json
import statistics
from importlib.resources import files
from pathlib import Path
from typing import Any

from kjnlae import Guard
from kjnlae.evaluation.model import classification_metrics
from kjnlae.evaluation.sandbox import run_scenarios


def metrics(labels: list[bool], predicted: list[bool]) -> dict[str, Any]:
    raw = classification_metrics([int(x) for x in labels], [int(x) for x in predicted])
    return {
        "count": len(labels),
        "confusion_matrix": {k: raw[k] for k in ("tp", "tn", "fp", "fn")},
        **{
            k: raw[k]
            for k in ("precision", "recall", "f1", "false_positive_rate", "false_negative_rate")
        },
    }


def benchmark(guard: Guard | None = None, dataset: Path | None = None) -> dict[str, Any]:
    raw = (
        dataset.read_bytes()
        if dataset
        else files("kjnlae.evaluation").joinpath("fixtures.json").read_bytes()
    )
    cases = json.loads(raw)
    if not isinstance(cases, list) or not 1 <= len(cases) <= 10000:
        raise ValueError("Dataset must contain 1..10000 examples")
    if any(type(case.get("attack")) is not bool for case in cases):
        raise ValueError("Explicit boolean labels required")
    scanner = guard or Guard()
    scans = [
        scanner.scan(case["text"], source=case.get("source", "retrieved_document"))
        for case in cases
    ]
    complete = [
        scan.inspection_complete and scan.detection_status != "INCOMPLETE" for scan in scans
    ]
    latencies = sorted(scan.latency_ms for scan in scans)
    detection: dict[str, Any] = {
        "status": "MEASURED" if all(complete) else "INCOMPLETE",
        "count": len(scans),
        "complete_count": sum(complete),
        "coverage": sum(complete) / len(scans),
        "latency_ms": {
            "mean": statistics.mean(latencies),
            "p95": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))],
        },
    }
    if all(complete):
        labels = [case["attack"] for case in cases]
        predictions = [scan.detection_status == "MALICIOUS_INDICATORS" for scan in scans]
        detection.update(metrics(labels, predictions))
        detection["per_category"] = {
            category: metrics(
                [labels[i] for i, c in enumerate(cases) if c["category"] == category],
                [predictions[i] for i, c in enumerate(cases) if c["category"] == category],
            )
            for category in sorted({case["category"] for case in cases})
        }
    scenarios = run_scenarios(scanner)
    attacks = [x for x in scenarios if x["malicious"]]
    benign = [x for x in scenarios if not x["malicious"]]
    report = {
        "dataset": {
            "name": str(dataset) if dataset else "kjnlae-original-regression-v1",
            "external": bool(dataset),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "count": len(cases),
            "attack_count": sum(c["attack"] for c in cases),
            "limitations": "Original regression fixtures; not a generalization estimate",
        },
        "detector": detection,
        "model": scanner.capabilities(),
        "defense": {
            "attack_count": len(attacks),
            "benign_count": len(benign),
            "attack_success_rate": sum(x["attack_succeeded"] for x in attacks) / len(attacks),
            "authorized_task_completion_rate": sum(x["completed"] for x in benign) / len(benign),
            "benign_task_rejection_rate": sum(not x["completed"] for x in benign) / len(benign),
            "unauthorized_action_prevention_rate": sum(not x["executed"] for x in attacks)
            / len(attacks),
            "mean_defense_overhead_ms": statistics.mean(x["defense_latency_ms"] for x in scenarios),
            "simulation": "Scripted proposals and synthetic local callback effects; no real LLM",
        },
        "scenarios": scenarios,
    }
    if guard is None:
        scanner.close()
    return report


def markdown_report(report: dict[str, Any]) -> str:
    detection = report["detector"]
    lines = [
        "# kjnlae measured fixture benchmark",
        "",
        f"Dataset: {report['dataset']['name']}",
        f"SHA256: {report['dataset']['sha256']}",
        f"Status: {detection['status']}",
        f"Coverage: {detection['complete_count']}/{detection['count']}",
        "",
    ]
    if detection["status"] == "MEASURED":
        lines.extend(
            [
                "| Precision | Recall | F1 | FPR | FNR |",
                "|---:|---:|---:|---:|---:|",
                "| "
                + " | ".join(
                    f"{detection[k]:.4f}"
                    for k in (
                        "precision",
                        "recall",
                        "f1",
                        "false_positive_rate",
                        "false_negative_rate",
                    )
                )
                + " |",
                "",
            ]
        )
    else:
        lines.append("Accuracy metrics withheld because model inspection was incomplete.\n")
    defense = report["defense"]
    lines.append(
        f"Unauthorized action prevention: {defense['unauthorized_action_prevention_rate']:.4f}"
    )
    lines.append(f"Authorized task completion: {defense['authorized_task_completion_rate']:.4f}")
    lines.append("Sandbox uses scripted proposals, not a live LLM or external benchmark.")
    return "\n".join(lines) + "\n"
