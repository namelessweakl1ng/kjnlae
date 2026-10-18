"""Report classifier quality without hiding incomplete model inspection."""

import math
from collections.abc import Mapping, Sequence
from typing import Any

from kjnlae.evaluation.comparison import summarize_scored_cases


def summarize_release(
    cases: Sequence[Mapping[str, Any]],
    scores: Sequence[float | None],
    *,
    threshold: float,
    latencies_ms: Sequence[float],
) -> dict[str, Any]:
    """Withhold whole-set accuracy if any case lacks a complete model score."""
    if (
        not cases
        or len(cases) != len(scores)
        or len(cases) != len(latencies_ms)
        or not 0 < threshold <= 1
        or any(not math.isfinite(latency) or latency < 0 for latency in latencies_ms)
        or any(
            score is not None and (not math.isfinite(score) or not 0 <= score <= 1)
            for score in scores
        )
    ):
        raise ValueError("Release evaluation requires aligned, bounded scores and latencies")
    complete_rows = [
        (case, score) for case, score in zip(cases, scores, strict=True) if score is not None
    ]
    incomplete_ids = [
        str(case["id"]) for case, score in zip(cases, scores, strict=True) if score is None
    ]
    observed = (
        summarize_scored_cases(
            [case for case, _ in complete_rows],
            [score for _, score in complete_rows],
            threshold=threshold,
        )
        if complete_rows
        else None
    )
    ordered = sorted(latencies_ms)
    result: dict[str, Any] = {
        "status": "MEASURED" if not incomplete_ids else "INCOMPLETE",
        "count": len(cases),
        "complete_count": len(complete_rows),
        "coverage": len(complete_rows) / len(cases),
        "incomplete_ids": incomplete_ids,
        "latency_ms": {
            "p50": ordered[math.ceil(len(ordered) * 0.5) - 1],
            "p95": ordered[math.ceil(len(ordered) * 0.95) - 1],
            "max": ordered[-1],
        },
        "metrics": observed["metrics"] if observed and not incomplete_ids else None,
        "observed_complete_only": observed,
    }
    if observed and not incomplete_ids:
        result["by_source"] = observed["by_source"]
        result["by_category"] = observed["by_category"]
        result["errors"] = observed["errors"]
        result["false_positive_rate_wilson_95"] = observed.get("false_positive_rate_wilson_95")
        result["recall_wilson_95"] = observed.get("recall_wilson_95")
    return result
