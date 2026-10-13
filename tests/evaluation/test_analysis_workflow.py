from kjnlae import Guard
from kjnlae.classifiers.local import LocalInference
from kjnlae.evaluation.sandbox import run_scenarios


class PositiveClassifier:
    def classify_views(self, views, source):
        return LocalInference("AVAILABLE", True, score=0.9)


def test_trusted_analysis_can_complete_public_read_despite_positive_scan():
    scenarios = {row["id"]: row for row in run_scenarios(Guard(classifier=PositiveClassifier()))}
    educational = scenarios["educational-document"]
    assert educational["detection_status"] == "MALICIOUS_INDICATORS"
    assert educational["detection_decision"] == "WARN"
    assert educational["completed"] is True
    assert educational["action_decision"] == "EXECUTED"
    assert all(not row["executed"] for row in scenarios.values() if row["malicious"])
