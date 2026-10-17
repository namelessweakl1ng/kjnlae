import numpy as np
import pytest

from kjnlae.classifiers.local import _scores_from_logits


def test_nonfinite_or_malformed_logits_cannot_clear_a_scan():
    for logits in (
        np.array([[0.0, float("nan")]]),
        np.array([[0.0, float("inf")]]),
        np.array([[0.0]]),
    ):
        with pytest.raises(ValueError, match="Invalid model logits"):
            _scores_from_logits(logits)


def test_stable_softmax_scores_binary_logits():
    assert _scores_from_logits(np.array([[0.0, 0.0], [1000.0, 0.0]])) == [0.5, 0.0]
