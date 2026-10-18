"""Select an experimental score threshold using calibration examples only."""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from kjnlae.evaluation.model import classification_metrics


@dataclass(frozen=True)
class OperatingPoint:
    threshold: float
    metrics: dict[str, float | int]
    candidates_checked: int


def select_operating_point(
    truth: Sequence[int], scores: Sequence[float], *, max_fpr: float, min_recall: float
) -> OperatingPoint:
    """Maximize recall, then minimize false alarms within predeclared limits.

    Scores are ranking values, not attack-success probabilities. Raises when
    no threshold meets both constraints, so callers cannot silently relax a
    release gate.
    """
    if (
        not truth
        or len(truth) != len(scores)
        or set(truth) != {0, 1}
        or not all(math.isfinite(s) and 0 <= s <= 1 for s in scores)
        or not 0 <= max_fpr <= 1
        or not 0 <= min_recall <= 1
    ):
        raise ValueError("Invalid calibration labels, scores, or limits")
    candidates = sorted(set(scores) | {0.5, 1.0})
    qualifying: list[OperatingPoint] = []
    for threshold in candidates:
        metrics = classification_metrics(truth, [int(score >= threshold) for score in scores])
        if metrics["false_positive_rate"] <= max_fpr and metrics["recall"] >= min_recall:
            qualifying.append(OperatingPoint(threshold, metrics, len(candidates)))
    if not qualifying:
        raise ValueError("No operating point meets both false-positive and recall limits")
    return max(
        qualifying,
        key=lambda point: (
            point.metrics["recall"],
            -point.metrics["false_positive_rate"],
            -abs(point.threshold - 0.5),
        ),
    )
