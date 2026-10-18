from types import SimpleNamespace

from kjnlae.evaluation.release_cases import EvaluationCase
from kjnlae.evaluation.release_runner import evaluate_cases


class IncompleteScanner:
    def scan(self, text, *, source):
        assert source == "user"
        return SimpleNamespace(
            inspection_complete=False,
            detection_status="INCOMPLETE",
            model_score=None,
            latency_ms=12.0,
            model_hash=None,
        )


class UnidentifiedScanner:
    def scan(self, text, *, source):
        return SimpleNamespace(
            inspection_complete=True,
            detection_status="CLEAN",
            model_score=0.1,
            latency_ms=2.0,
            model_hash=None,
        )


def test_release_runner_withholds_accuracy_for_incomplete_scan():
    case = EvaluationCase(
        id="tail",
        family_id="tail",
        text="A full document with a tail attack",
        label=1,
        source="user",
        category="tail",
        provenance="original-mit",
    )
    report = evaluate_cases(IncompleteScanner(), [case], threshold=0.5)
    assert report["status"] == "INCOMPLETE"
    assert report["metrics"] is None
    assert report["incomplete_ids"] == ["tail"]
    unidentified = evaluate_cases(UnidentifiedScanner(), [case], threshold=0.5)
    assert unidentified["status"] == "INCOMPLETE"
