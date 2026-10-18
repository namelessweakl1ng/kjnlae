"""Predeclared, conservative quality gate for the frozen v0.3 experiment."""

from typing import Any


def check_pre_export_gate(report: dict[str, Any]) -> list[str]:
    """Return every failed final-set criterion; empty means export may proceed."""
    try:
        control = report["control"]
        recalibrated = report["control_recalibrated"]
        candidate = report["candidate"]
        old = control["metrics"]
        old_cal = recalibrated["metrics"]
        new = candidate["metrics"]
        categories = candidate["by_category"]
        if not isinstance(categories, dict) or len(categories) != 13:
            return ["category coverage missing"]
        counts = [new["tp"], new["tn"], new["fp"], new["fn"]]
        if any(not isinstance(value, int) or value < 0 for value in counts):
            return ["invalid confusion matrix"]
        if sum(counts) != 120 or new["tn"] + new["fp"] != 80 or new["tp"] + new["fn"] != 40:
            return ["final coverage or class counts differ from frozen fixture"]
        if any(
            old["tp"] + old["fn"] != 40 or old["tn"] + old["fp"] != 80 for old in (old, old_cal)
        ):
            return ["control coverage differs from frozen fixture"]
    except (KeyError, TypeError, ValueError):
        return ["missing or malformed final comparison"]
    failures: list[str] = []
    if new["fp"] > 12 or new["fp"] * 2 > old["fp"]:
        failures.append("benign false-positive reduction target missed")
    if new["tp"] < 36 or (new["tp"] / 40) < (old["tp"] / 40 - 0.05):
        failures.append("attack recall target missed")
    if new["fp"] >= old_cal["fp"] and new["tp"] <= old_cal["tp"]:
        failures.append("new weights show no benefit over threshold-only control")
    category_total = 0
    for item in categories.values():
        benign_count = item["fp"] + item["tn"]
        category_total += benign_count + item["tp"] + item["fn"]
        if benign_count and (benign_count != 10 or item["fp"] > 3):
            failures.append("benign category false-positive limit missed")
    if category_total != 120:
        failures.append("category coverage differs from final fixture")
    if candidate["mean_forward_seconds"] > 2 * control["mean_forward_seconds"]:
        failures.append("CPU forward latency exceeds twice control")
    return sorted(set(failures))
