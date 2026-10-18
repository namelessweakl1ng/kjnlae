import json

from kjnlae.training.augment import augment_benign_sources


def test_augmentation_keeps_train_label_and_family(tmp_path):
    source = tmp_path / "train.jsonl"
    source.write_text(
        json.dumps(
            {
                "id": "public-benign-1",
                "text": "The office opens on Monday.",
                "source": "user",
                "label": 0,
                "split": "TRAIN",
                "family_id": "public-benign-1",
                "provenance_id": "deepset-4f61ecb",
            }
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    output = tmp_path / "augmented.jsonl"
    count = augment_benign_sources(source, output, count=1, seed=7)
    row = json.loads(output.read_text(encoding="utf-8"))
    assert count == 1
    assert row["label"] == 0
    assert row["split"] == "TRAIN"
    assert row["family_id"] == "public-benign-1"
    assert row["source"] != "user"


def test_augmentation_rejects_non_train_input(tmp_path):
    source = tmp_path / "bad.jsonl"
    source.write_text(
        json.dumps(
            {
                "id": "test-case",
                "text": "Secret test text.",
                "source": "user",
                "label": 0,
                "split": "HELD_OUT_TEST",
                "family_id": "test-case",
                "provenance_id": "deepset-4f61ecb",
            }
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    output = tmp_path / "augmented.jsonl"
    try:
        augment_benign_sources(source, output, count=1)
    except ValueError as exc:
        assert "TRAIN" in str(exc)
    else:
        raise AssertionError("A held-out example entered augmentation")
