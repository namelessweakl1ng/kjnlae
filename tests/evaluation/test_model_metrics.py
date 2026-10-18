from pathlib import Path

import pytest

from kjnlae.evaluation.model import (
    calibrate_threshold,
    classification_metrics,
    validate_evaluation_splits,
)


def test_metrics_count_errors_and_denominators() -> None:
    result = classification_metrics([1, 1, 0, 0], [1, 0, 1, 0])
    assert result["tp"] == result["fp"] == result["fn"] == result["tn"] == 1
    assert result["precision"] == result["recall"] == result["f1"] == 0.5
    assert result["false_positive_rate"] == result["false_negative_rate"] == 0.5


def test_threshold_uses_only_supplied_calibration_rows() -> None:
    selected = calibrate_threshold([0, 0, 1, 1], [0.1, 0.2, 0.6, 0.8])
    assert 0.2 < selected <= 0.6


def test_evaluation_rejects_calibration_test_leakage(tmp_path: Path) -> None:
    cal = tmp_path / "calibration.jsonl"
    test = tmp_path / "held_out_test.jsonl"
    cal.write_text(
        '{"id":"same","split":"CALIBRATION","text":"x","label":1}\n', encoding="utf-8", newline="\n"
    )
    test.write_text(
        '{"id":"same","split":"HELD_OUT_TEST","text":"y","label":0}\n',
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(ValueError, match="leakage"):
        validate_evaluation_splits(cal, test)
