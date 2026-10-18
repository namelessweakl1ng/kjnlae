import pytest

from kjnlae.evaluation.operating_point import select_operating_point


def test_threshold_is_lowest_that_meets_false_alarm_and_recall_limits():
    truth = [0] * 10 + [1] * 10
    scores = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.30]
    scores += [0.15, 0.20, 0.25, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95]
    result = select_operating_point(truth, scores, max_fpr=0.1, min_recall=0.9)
    assert result.threshold == 0.15
    assert result.metrics["fp"] == 1
    assert result.metrics["fn"] == 0


def test_threshold_refuses_unachievable_tradeoff():
    with pytest.raises(ValueError, match="No operating point"):
        select_operating_point([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1], max_fpr=0, min_recall=1)


def test_equal_recall_prefers_fewer_false_alarms():
    result = select_operating_point([0, 0, 1, 1], [0.2, 0.4, 0.5, 0.9], max_fpr=0.5, min_recall=1)
    assert result.threshold == 0.5
    assert result.metrics["fp"] == 0


def test_threshold_rejects_nonfinite_or_one_class_scores():
    with pytest.raises(ValueError):
        select_operating_point([0, 1], [float("nan"), 0.8], max_fpr=0.1, min_recall=0.9)
    with pytest.raises(ValueError):
        select_operating_point([0, 0], [0.2, 0.3], max_fpr=0.1, min_recall=0.9)
