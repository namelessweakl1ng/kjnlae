from pathlib import Path
from runpy import run_path

import pytest

load_rows = run_path(str(Path(__file__).resolve().parents[2] / "scripts/compare_runtimes.py"))[
    "load_rows"
]


def test_parity_loader_accepts_frozen_fixture():
    path = Path(__file__).resolve().parents[2] / "datasets/fixtures/v0.2-independent-eval.json"
    rows = load_rows(path)
    assert len(rows) == 50
    assert {row["label"] for row in rows} == {0, 1}
    assert all(row["source"] and row["text"] for row in rows)


def test_parity_loader_requires_pinned_heldout_parquet(tmp_path):
    path = tmp_path / "untrusted.parquet"
    path.write_bytes(b"untrusted")
    with pytest.raises(ValueError, match="Deepset source SHA256"):
        load_rows(path)
