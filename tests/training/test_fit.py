from pathlib import Path

import pytest

from kjnlae.training.fit import FitConfig, class_weights, validate_partitions


def test_fit_cannot_train_on_validation_rows(tmp_path: Path) -> None:
    train = tmp_path / "train.jsonl"
    validation = tmp_path / "validation.jsonl"
    train.write_text('{"split":"VALIDATION","label":1}\n', encoding="utf-8", newline="\n")
    validation.write_text('{"split":"VALIDATION","label":0}\n', encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match="TRAIN"):
        validate_partitions(train, validation)


def test_class_weights_come_from_training_counts() -> None:
    assert class_weights([0, 0, 1, 1]) == (1.0, 1.0)
    assert class_weights([0, 1, 1, 1]) == (2.0, 2 / 3)
    with pytest.raises(ValueError):
        class_weights([1, 1])


def test_training_limits_are_finite(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        FitConfig(tmp_path, tmp_path, tmp_path, tmp_path, epochs=0)
    with pytest.raises(ValueError):
        FitConfig(tmp_path, tmp_path, tmp_path, tmp_path, max_tokens=512)
