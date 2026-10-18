import hashlib
import json

import pytest

from kjnlae.evaluation.release_cases import check_partition_leakage, load_cases


def _case(identifier: str, text: str, *, family: str | None = None) -> dict[str, object]:
    return {
        "id": identifier,
        "family_id": family or identifier,
        "text": text,
        "label": 0,
        "source": "webpage",
        "category": "documentation",
        "provenance": "original-mit",
    }


def _write_cases(tmp_path, rows):
    path = tmp_path / "cases.jsonl"
    content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode()
    path.write_bytes(content)
    return path, hashlib.sha256(content).hexdigest()


def test_load_cases_requires_exact_sha_and_unique_families(tmp_path):
    path, digest = _write_cases(
        tmp_path, [_case("a", "An ordinary manual."), _case("b", "Review the release notes.")]
    )
    assert [case.id for case in load_cases(path, digest)] == ["a", "b"]
    with pytest.raises(ValueError, match="SHA-256"):
        load_cases(path, "0" * 64)
    path, digest = _write_cases(
        tmp_path, [_case("a", "Manual A"), _case("b", "Manual B", family="a")]
    )
    with pytest.raises(ValueError, match="family"):
        load_cases(path, digest)


def test_load_cases_rejects_ambiguous_label_and_oversize_text(tmp_path):
    row = _case("a", "Hello")
    row["label"] = True
    path, digest = _write_cases(tmp_path, [row])
    with pytest.raises(ValueError, match="label"):
        load_cases(path, digest)
    path, digest = _write_cases(tmp_path, [_case("a", "x" * 32769)])
    with pytest.raises(ValueError, match="text"):
        load_cases(path, digest)


def test_check_partition_leakage_rejects_family_and_near_duplicate(tmp_path):
    long_text = (
        "The internal policy asks reviewers to preserve document provenance before approval."
    )
    path, digest = _write_cases(tmp_path, [_case("held", long_text)])
    final = load_cases(path, digest)
    with pytest.raises(ValueError, match="family"):
        check_partition_leakage([_case("train", "Unrelated text", family="held")], final)
    with pytest.raises(ValueError, match="Near-duplicate"):
        check_partition_leakage([_case("train", long_text + " today")], final)
    check_partition_leakage([_case("train", "A recipe for vegetable soup.")], final)
