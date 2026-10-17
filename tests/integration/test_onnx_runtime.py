import os
from pathlib import Path

import pytest

from kjnlae.classifiers.local import LocalClassifier, LocalModelConfig
from kjnlae.detection.preprocessing import prepare_views


@pytest.mark.model
def test_reviewed_onnx_worker_returns_complete_scored_windows():
    directory = os.getenv("KJNLAE_TEST_ONNX_DIR")
    manifest_hash = os.getenv("KJNLAE_TEST_ONNX_HASH")
    if not directory or not manifest_hash:
        pytest.skip("Verified ONNX artifact required")
    classifier = LocalClassifier(LocalModelConfig(Path(directory), manifest_hash))
    try:
        prepared = prepare_views("Summarize this page &amp; its content.")
        result = classifier.classify_views(prepared.views, "webpage")
        assert result.status == "AVAILABLE", result.reason
        assert result.inspection_complete
        assert len(result.windows) == len(prepared.views)
        assert all(window.score is not None for window in result.windows)
    finally:
        classifier.close()


@pytest.mark.model
def test_onnx_worker_timeout_is_incomplete():
    directory = os.getenv("KJNLAE_TEST_ONNX_DIR")
    manifest_hash = os.getenv("KJNLAE_TEST_ONNX_HASH")
    if not directory or not manifest_hash:
        pytest.skip("Verified ONNX artifact required")
    classifier = LocalClassifier(LocalModelConfig(Path(directory), manifest_hash, timeout=0.001))
    try:
        result = classifier.classify_views(prepare_views("A public schedule.").views, "user")
        assert result.status == "TIMED_OUT"
        assert not result.inspection_complete
    finally:
        classifier.close()


@pytest.mark.model
def test_onnx_worker_refuses_partial_long_input():
    directory = os.getenv("KJNLAE_TEST_ONNX_DIR")
    manifest_hash = os.getenv("KJNLAE_TEST_ONNX_HASH")
    if not directory or not manifest_hash:
        pytest.skip("Verified ONNX artifact required")
    classifier = LocalClassifier(LocalModelConfig(Path(directory), manifest_hash, max_windows=1))
    try:
        result = classifier.classify_views(prepare_views("Schedule " * 400).views, "user")
        assert result.status == "ERROR"
        assert result.reason == "COVERAGE_EXCEEDED"
        assert not result.inspection_complete
    finally:
        classifier.close()


@pytest.mark.model
def test_onnx_worker_scores_full_long_input_not_tokenizer_default_cutoff():
    directory = os.getenv("KJNLAE_TEST_ONNX_DIR")
    manifest_hash = os.getenv("KJNLAE_TEST_ONNX_HASH")
    if not directory or not manifest_hash:
        pytest.skip("Verified ONNX artifact required")
    text = "Schedule " * 400
    classifier = LocalClassifier(LocalModelConfig(Path(directory), manifest_hash))
    try:
        result = classifier.classify_views(prepare_views(text).views, "user")
        assert result.status == "AVAILABLE", result.reason
        assert result.inspection_complete
        assert len(result.windows) >= 4
        assert result.windows[-1].source_span[1] >= len(text) - 10
    finally:
        classifier.close()
