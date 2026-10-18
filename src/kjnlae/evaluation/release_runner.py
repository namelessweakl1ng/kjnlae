"""Run bounded actual-model evaluation through the SDK inspection path."""

from collections.abc import Sequence
from typing import Any, Protocol

from kjnlae.evaluation.release_cases import EvaluationCase
from kjnlae.evaluation.release_report import summarize_release
from kjnlae.schemas import Source
from kjnlae.schemas_v2 import InspectionResultV2


class Scanner(Protocol):
    def scan(self, text: str, *, source: Source) -> InspectionResultV2: ...


def evaluate_cases(
    scanner: Scanner, cases: Sequence[EvaluationCase], *, threshold: float
) -> dict[str, Any]:
    """Record every result; incomplete inspection never enters whole-set metrics."""
    scores: list[float | None] = []
    latencies: list[float] = []
    model_hashes: set[str] = set()
    for case in cases:
        result = scanner.scan(case.text, source=case.source)
        complete = (
            result.inspection_complete
            and result.detection_status != "INCOMPLETE"
            and result.model_score is not None
            and result.model_hash is not None
        )
        scores.append(result.model_score if complete else None)
        latencies.append(result.latency_ms)
        if complete and result.model_hash is not None:
            model_hashes.add(result.model_hash)
    if len(model_hashes) > 1:
        raise ValueError("Model identity changed during release evaluation")
    report = summarize_release(
        [case.model_dump() for case in cases], scores, threshold=threshold, latencies_ms=latencies
    )
    report["model_hash"] = next(iter(model_hashes), None)
    return report
