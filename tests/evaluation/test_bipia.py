import json

import pytest

from kjnlae.evaluation.bipia import import_export


def test_import_explicit_bipia_context_and_attack_metadata(tmp_path):
    path = tmp_path / "builder.jsonl"
    path.write_text(
        json.dumps(
            {
                "context": "article + attack",
                "attack_name": "override-0",
                "attack_str": "attack",
                "task_name": "qa",
            }
        )
        + "\n"
    )
    cases = import_export(path)
    assert cases[0]["attack"] is True and cases[0]["text"] == "article + attack"
    assert cases[0]["provenance"]["adapter"] == "BIPIA-builder-export"


def test_unknown_label_not_assumed_malicious(tmp_path):
    path = tmp_path / "unknown.jsonl"
    path.write_text('{"context":"hello"}\n')
    with pytest.raises(ValueError):
        import_export(path)
