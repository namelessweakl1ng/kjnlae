from kjnlae.evaluation.benchmark import benchmark, metrics
from kjnlae.evaluation.sandbox import run_scenarios


def test_metric_denominators():
    result = metrics([True, True, False, False], [True, False, True, False])
    assert result["confusion_matrix"] == {"tp": 1, "fn": 1, "fp": 1, "tn": 1}
    assert result["precision"] == result["recall"] == result["f1"] == 0.5
    assert result["false_positive_rate"] == result["false_negative_rate"] == 0.5


def test_missing_model_withholds_accuracy_and_independent_actions_still_deny(monkeypatch):
    monkeypatch.delenv("KJNLAE_MODEL_DIR", raising=False)
    monkeypatch.delenv("KJNLAE_MODEL_HASH", raising=False)
    report = benchmark()
    assert report["detector"]["status"] == "INCOMPLETE"
    assert "f1" not in report["detector"]
    assert report["defense"]["unauthorized_action_prevention_rate"] == 1
    bypass = next(s for s in run_scenarios() if s["id"] == "detector-bypass")
    assert bypass["action_decision"] == "DENIED"
    assert not bypass["attack_succeeded"]
