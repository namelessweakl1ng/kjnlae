from kjnlae.evaluation.comparison import summarize_scored_cases, wilson_interval


def test_comparison_reports_false_alarm_categories_and_sources():
    rows = [
        {"id": "quoted", "label": 0, "source": "webpage", "category": "quoted"},
        {"id": "normal", "label": 0, "source": "email", "category": "ordinary"},
        {"id": "attack", "label": 1, "source": "webpage", "category": "role_spoof"},
    ]
    result = summarize_scored_cases(rows, [0.8, 0.1, 0.9], threshold=0.5)
    assert result["metrics"]["fp"] == 1
    assert result["by_category"]["quoted"]["fp"] == 1
    assert result["by_source"]["webpage"]["tp"] == 1
    assert result["errors"] == [{"id": "quoted", "label": 0, "score": 0.8}]


def test_wilson_interval_contains_observed_rate():
    low, high = wilson_interval(3, 10)
    assert 0 < low < 0.3 < high < 1
