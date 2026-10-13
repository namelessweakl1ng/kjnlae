from pathlib import Path

from kjnlae.classifiers.local import LocalClassifier, LocalModelConfig, build_windows
from kjnlae.detection.preprocessing import InspectionView


def test_build_windows_covers_late_view_without_dropping_it() -> None:
    first = InspectionView("original", "abcdefgh", tuple((i, i + 1) for i in range(8)))
    late = InspectionView("base64", "secret", tuple(((12, 24),) * 6))
    windows = build_windows(
        [first, late],
        tokenized=[([(i, i + 1) for i in range(8)]), [(i, i + 1) for i in range(6)]],
        width=4,
        overlap=1,
        max_windows=8,
    )
    assert windows is not None
    assert windows[-1].view == "base64"
    assert windows[-1].source_span == (12, 24)
    assert (
        build_windows(
            [first, late], [[(i, i + 1) for i in range(8)], [(i, i + 1) for i in range(6)]], 4, 1, 2
        )
        is None
    )


def test_missing_trained_artifact_is_explicit(tmp_path: Path) -> None:
    classifier = LocalClassifier(LocalModelConfig(tmp_path / "missing", "f" * 64))
    result = classifier.classify_views([InspectionView("original", "hello", ((0, 1),) * 5)], "user")
    assert result.status == "MISSING"
    assert result.inspection_complete is False
