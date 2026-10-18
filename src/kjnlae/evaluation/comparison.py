"""Transparent per-group metrics for genuine model score comparisons."""

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from kjnlae.evaluation.model import classification_metrics


def wilson_interval(successes: int, count: int, z: float = 1.96) -> tuple[float, float]:
    """Return a descriptive binomial interval; correlated fixtures weaken coverage."""
    if count <= 0 or not 0 <= successes <= count:
        raise ValueError("Invalid Wilson interval counts")
    p = successes / count
    z2 = z * z
    center = (p + z2 / (2 * count)) / (1 + z2 / count)
    margin = z * math.sqrt(p * (1 - p) / count + z2 / (4 * count * count))
    margin /= 1 + z2 / count
    return max(0.0, center - margin), min(1.0, center + margin)


def _quantiles(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    if not ordered:
        return {}
    return {
        name: ordered[round((len(ordered) - 1) * fraction)]
        for name, fraction in (("p05", 0.05), ("median", 0.5), ("p95", 0.95))
    }


def summarize_scored_cases(
    rows: Sequence[Mapping[str, Any]], scores: Sequence[float], *, threshold: float
) -> dict[str, Any]:
    """Summarize complete labeled cases and show every classification mistake."""
    if (
        not rows
        or len(rows) != len(scores)
        or not 0 < threshold <= 1
        or any(row.get("label") not in (0, 1) for row in rows)
        or any(not math.isfinite(score) or not 0 <= score <= 1 for score in scores)
    ):
        raise ValueError("Invalid or incomplete scored cases")
    truth = [int(row["label"]) for row in rows]
    predicted = [int(score >= threshold) for score in scores]
    metrics = classification_metrics(truth, predicted)
    groups: dict[str, dict[str, Any]] = {}
    for field, result_name in (("category", "by_category"), ("source", "by_source")):
        buckets: dict[str, list[int]] = defaultdict(list)
        for index, row in enumerate(rows):
            buckets[str(row.get(field, "unspecified"))].append(index)
        groups[result_name] = {
            name: classification_metrics(
                [truth[i] for i in indices], [predicted[i] for i in indices]
            )
            for name, indices in sorted(buckets.items())
        }
    benign = [score for row, score in zip(rows, scores, strict=True) if row["label"] == 0]
    attacks = [score for row, score in zip(rows, scores, strict=True) if row["label"] == 1]
    result: dict[str, Any] = {
        "threshold": threshold,
        "count": len(rows),
        "metrics": metrics,
        **groups,
        "score_quantiles": {"benign": _quantiles(benign), "attack": _quantiles(attacks)},
        "errors": [
            {"id": row["id"], "label": row["label"], "score": score}
            for row, score, pred in zip(rows, scores, predicted, strict=True)
            if pred != row["label"]
        ],
    }
    if benign:
        result["false_positive_rate_wilson_95"] = wilson_interval(int(metrics["fp"]), len(benign))
    if attacks:
        result["recall_wilson_95"] = wilson_interval(int(metrics["tp"]), len(attacks))
    return result
