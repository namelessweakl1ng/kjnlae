from kjnlae.evaluation.benchmark import benchmark, metrics
from kjnlae.evaluation.sandbox import run_scenarios
from kjnlae.storage.sqlite import SQLiteHistory


def test_metric_denominators():
    r = metrics([True, True, False, False], [True, False, True, False])
    assert r["confusion_matrix"] == {"tp": 1, "fn": 1, "fp": 1, "tn": 1}
    assert r["precision"] == r["recall"] == r["f1"] == 0.5
    assert r["false_positive_rate"] == r["false_negative_rate"] == 0.5


def test_bypass_blocked_by_authorization():
    cases = run_scenarios()
    bypass = next(s for s in cases if s["id"] == "detector-bypass")
    assert bypass["scan"]["decision"] == "ALLOW"
    assert bypass["authorization"]["decision"] == "BLOCK"
    assert bypass["unguarded_attack_succeeded"] is True
    assert bypass["attack_succeeded"] is False


def test_benchmark_real_counts_and_model_not_run():
    report = benchmark()
    assert report["detectors"]["deterministic"]["count"] >= 20
    assert report["detectors"]["ml"]["status"] == "not_run"
    assert report["defense"]["unauthorized_action_prevention_rate"] == 1


def test_sqlite_retention(tmp_path):
    db = SQLiteHistory(str(tmp_path / "a.db"), retention=2)
    for i in range(3):
        db.record(
            {
                "decision": "ALLOW",
                "source": "user",
                "findings": [],
                "latency_ms": i,
                "text": "secret",
                "classification": None,
            }
        )
    assert len(db.list()) == 2
    assert all("text" not in r for r in db.list())
    db.clear()
    assert db.list() == []
