from pathlib import Path

import pytest

from kjnlae.training.probe import ProbeConfig, check_resources, run_probe


def test_probe_rejects_non_train_or_insufficient_examples(tmp_path: Path) -> None:
    data = tmp_path / "train.jsonl"
    data.write_text('{"id":"1","split":"VALIDATION","text":"hello","label":0}\n')
    with pytest.raises(ValueError, match="TRAIN"):
        run_probe(ProbeConfig(tmp_path / "base", data, tmp_path / "out"))


def test_resource_stops_are_fail_closed() -> None:
    assert check_resources(worker_rss=13 * 1024**3, cgroup=1, disk_free=20 * 1024**3)
    assert check_resources(worker_rss=1, cgroup=29 * 1024**3, disk_free=20 * 1024**3)
    assert check_resources(worker_rss=1, cgroup=1, disk_free=7 * 1024**3)
    assert not check_resources(worker_rss=1, cgroup=1, disk_free=20 * 1024**3)
