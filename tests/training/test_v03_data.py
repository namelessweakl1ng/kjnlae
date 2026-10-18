import json
from pathlib import Path

from kjnlae.training.v03_data import authored_rows, reject_frozen_overlap


def test_v03_authored_partitions_are_family_disjoint_and_source_balanced():
    rows = authored_rows()
    assert len(rows) >= 250
    assert len({row.id for row in rows}) == len(rows)
    families: dict[str, str] = {}
    for row in rows:
        assert families.setdefault(row.family_id, row.split) == row.split
    for split in ("TRAIN", "VALIDATION", "CALIBRATION"):
        selected = [row for row in rows if row.split == split]
        assert len(selected) >= 40
        assert {row.label for row in selected} == {0, 1}
        assert {row.source for row in selected if row.label == 0} >= {
            "retrieved_document",
            "webpage",
            "email",
            "tool_response",
        }
        assert {row.source for row in selected if row.label == 1} >= {
            "retrieved_document",
            "webpage",
            "email",
            "tool_response",
        }


def test_v03_authored_text_never_copies_frozen_final_case():
    root = Path(__file__).resolve().parents[2]
    final = {
        json.loads(line)["text"].casefold()
        for line in (root / "datasets/fixtures/v0.3-frozen-final.jsonl").read_text().splitlines()
    }
    assert not ({row.text.casefold() for row in authored_rows()} & final)


def test_frozen_separation_rejects_near_duplicate_even_with_different_source():
    rows = authored_rows()
    final = [{"text": rows[0].text + "!", "id": "hidden-final"}]
    try:
        reject_frozen_overlap(rows, final)
    except ValueError as exc:
        assert "hidden-final" in str(exc)
    else:
        raise AssertionError("near-duplicate leaked into training data")
