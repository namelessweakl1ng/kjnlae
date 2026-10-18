from kjnlae.evaluation.v03_gate import check_pre_export_gate


def _report():
    categories = {f"benign_{i}": {"fp": 1, "tn": 9, "tp": 0, "fn": 0} for i in range(8)}
    categories["benign_0"] = {"fp": 2, "tn": 8, "tp": 0, "fn": 0}
    categories.update({f"attack_{i}": {"fp": 0, "tn": 0, "tp": 8, "fn": 0} for i in range(5)})
    benign = {"by_category": categories}
    return {
        "control": {
            "metrics": {"tp": 40, "tn": 46, "fp": 34, "fn": 0},
            "mean_forward_seconds": 0.03,
        },
        "control_recalibrated": {"metrics": {"tp": 40, "tn": 64, "fp": 16, "fn": 0}},
        "candidate": {
            "metrics": {"tp": 40, "tn": 71, "fp": 9, "fn": 0},
            "mean_forward_seconds": 0.04,
            **benign,
        },
    }


def test_release_gate_accepts_bounded_reduction_without_recall_loss():
    assert check_pre_export_gate(_report()) == []


def test_release_gate_rejects_category_or_coverage_failure():
    report = _report()
    report["candidate"]["by_category"]["benign_0"]["fp"] = 4
    assert "category" in " ".join(check_pre_export_gate(report))
    report = _report()
    report["candidate"]["metrics"]["tn"] = 70
    assert "coverage" in " ".join(check_pre_export_gate(report))
