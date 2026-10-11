"""Measured fixture metrics. No external benchmark or probability calibration claims."""

import hashlib
import json
import statistics
from importlib.resources import files
from pathlib import Path
from time import perf_counter
from typing import Any

from kjnlae import Guard
from kjnlae.evaluation.sandbox import run_scenarios


def metrics(labels: list[bool], predicted: list[bool]) -> dict[str, Any]:
    if len(labels) != len(predicted) or not labels:
        raise ValueError("Nonempty paired labels required")
    tp = sum(a and b for a, b in zip(labels, predicted, strict=True))
    fn = sum(a and not b for a, b in zip(labels, predicted, strict=True))
    fp = sum(not a and b for a, b in zip(labels, predicted, strict=True))
    tn = sum(not a and not b for a, b in zip(labels, predicted, strict=True))
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    return {
        "count": len(labels),
        "confusion_matrix": {"tp": tp, "fn": fn, "fp": fp, "tn": tn},
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
        "false_positive_rate": fp / (fp + tn) if fp + tn else 0,
        "false_negative_rate": fn / (fn + tp) if fn + tp else 0,
    }


def benchmark(guard: Guard | None = None, dataset: Path | None = None) -> dict[str, Any]:
    raw = (
        dataset.read_bytes()
        if dataset
        else files("kjnlae.evaluation").joinpath("fixtures.json").read_bytes()
    )
    cases = json.loads(raw)
    if not isinstance(cases, list) or not 1 <= len(cases) <= 10000:
        raise ValueError("Dataset must contain 1..10000 cases")
    detector = guard or Guard()
    results: dict[str, Any] = {}
    for mode in ("deterministic", "ml", "combined"):
        if mode != "deterministic" and detector.classifier is None:
            results[mode] = {"status": "not_run", "reason": "No actual model configured"}
            continue
        scans = [
            detector.scan(
                c["text"],
                source=c.get("source", "retrieved_document"),
                purpose=c.get("purpose", "reference"),
                mode=mode,
            )
            for c in cases
        ]
        labels = [c["attack"] for c in cases]
        if not all(type(label) is bool for label in labels):
            raise ValueError("Explicit boolean attack labels required")
        predictions = [s.decision in {"BLOCK", "REQUIRE_REVIEW"} for s in scans]
        available = [
            s.classification is None or s.classification.status == "available" for s in scans
        ]
        coverage = sum(s.inspection_complete for s in scans) / len(scans)
        if not all(available):
            results[mode] = {
                "status": "incomplete",
                "count": len(scans),
                "coverage": coverage,
                "reason": "Classifier unavailable for some cases; no accuracy estimate",
                "incomplete_inputs": sum(not s.inspection_complete for s in scans),
            }
            continue
        latencies = sorted(s.latency_ms for s in scans)
        per_category = {}
        for category in sorted({c["category"] for c in cases}):
            idx = [i for i, c in enumerate(cases) if c["category"] == category]
            per_category[category] = metrics(
                [labels[i] for i in idx], [predictions[i] for i in idx]
            )
        results[mode] = {
            **metrics(labels, predictions),
            "status": "complete" if all(available) else "degraded",
            "coverage": coverage,
            "truncated_inputs": 0,
            "incomplete_inputs": sum(not s.inspection_complete for s in scans),
            "per_category": per_category,
            "latency_ms": {
                "mean": statistics.mean(latencies),
                "p95": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))],
            },
            "cases": [
                {
                    "id": c["id"],
                    "expected_attack": label,
                    "predicted_attack": p,
                    "decision": s.decision,
                    "complete": s.inspection_complete,
                }
                for c, label, p, s in zip(cases, labels, predictions, scans, strict=True)
            ],
        }
    scenarios = run_scenarios(detector)
    attacks = [s for s in scenarios if s["malicious"]]
    benign = [s for s in scenarios if not s["malicious"]]
    # Probe the same boundary under required-control failure.
    from kjnlae.guards.actions import ActionGateway, Authority, Grant
    from kjnlae.schemas import Action

    action = Action(tool="send_email", resource="public", destination="bob@example.test")
    ctx = Authority(
        "probe", frozenset({"public"}), (Grant(action),), frozenset({"bob@example.test"})
    )
    gw = ActionGateway()
    started = perf_counter()
    failure = gw.authorize(action, ctx, gw.approve(action, ctx), controls_ready=False)
    return {
        "dataset": {
            "name": str(dataset) if dataset else "kjnlae-original-regression-v1",
            "external": dataset is not None,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "count": len(cases),
            "attack_count": sum(c["attack"] for c in cases),
            "limitations": "Hand-authored regression cases; no held-out generalization estimate",
        },
        "positive_definition": "BLOCK or REQUIRE_REVIEW (WARN is negative)",
        "detectors": results,
        "defense": {
            "attack_count": len(attacks),
            "benign_count": len(benign),
            "attack_success_rate": sum(s["attack_succeeded"] for s in attacks) / len(attacks),
            "authorized_task_completion_rate": sum(s["completed"] for s in benign) / len(benign),
            "benign_task_rejection_rate": sum(not s["completed"] for s in benign) / len(benign),
            "unauthorized_action_prevention_rate": sum(not s["executed"] for s in attacks)
            / len(attacks),
            "control_failure_decision": failure.decision,
            "control_failure_latency_ms": (perf_counter() - started) * 1000,
            "mean_defense_overhead_ms": statistics.mean(s["defense_latency_ms"] for s in scenarios),
            "simulation": "Scripted local tool proposals; no actual LLM benchmark",
        },
        "model": getattr(detector.classifier, "provenance", lambda: None)(),
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# kjnlae measured benchmark",
        "",
        f"Dataset: {report['dataset']['name']}",
        f"SHA256: {report['dataset']['sha256']}",
        "",
        report["dataset"]["limitations"],
        "",
        "| Detector | Precision | Recall | F1 | FPR | FNR |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for mode, result in report["detectors"].items():
        if "precision" in result:
            lines.append(
                f"| {mode} | "
                + " | ".join(
                    f"{result[k]:.4f}"
                    for k in (
                        "precision",
                        "recall",
                        "f1",
                        "false_positive_rate",
                        "false_negative_rate",
                    )
                )
                + " |"
            )
        else:
            lines.append(f"| {mode} | {result['status']} | — | — | — | — |")
    lines.extend(
        [
            "",
            "## Defense (six synthetic scenarios)",
            "",
            "```json",
            json.dumps(report["defense"], indent=2),
            "```",
            "",
            "These results do not establish resistance of any real LLM or external benchmark.",
        ]
    )
    return "\n".join(lines) + "\n"
