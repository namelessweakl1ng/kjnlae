import os
from pathlib import Path

import pytest

from kjnlae.classifiers.local import LocalClassifier, LocalModelConfig
from kjnlae.detection.preprocessing import prepare_views
from kjnlae.evaluation.model import _score_rows


@pytest.mark.model
def test_real_weight_single_window_inference() -> None:
    model_path = os.getenv("KJNLAE_TEST_MODEL_DIR")
    if not model_path:
        pytest.skip("Set KJNLAE_TEST_MODEL_DIR to local real weights")
    scores, latencies = _score_rows(
        Path(model_path),
        [{"id": "smoke", "source": "user", "text": "Summarize this page", "label": 0}],
    )
    assert len(scores) == len(latencies) == 1
    assert 0 <= scores[0] <= 1


@pytest.mark.model
def test_verified_trained_model_scans_all_views() -> None:
    model_path = os.getenv("KJNLAE_TEST_MODEL_DIR")
    manifest_hash = os.getenv("KJNLAE_TEST_MODEL_HASH")
    if not model_path or not manifest_hash:
        pytest.skip("Set both local trained model path and manifest hash")
    classifier = LocalClassifier(LocalModelConfig(Path(model_path), manifest_hash))
    try:
        prepared = prepare_views("Read this page &amp; its content.")
        inference = classifier.classify_views(prepared.views, "webpage")
        assert inference.status == "AVAILABLE", inference.reason
        assert inference.inspection_complete
        assert {item.view for item in inference.windows} == {v.name for v in prepared.views}
    finally:
        classifier.close()
