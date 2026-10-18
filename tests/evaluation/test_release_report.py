from kjnlae.evaluation.release_report import summarize_release


def test_release_report_preserves_incomplete_and_grouped_errors():
    cases = [
        {"id": "benign", "family_id": "a", "label": 0, "source": "email", "category": "normal"},
        {"id": "attack", "family_id": "b", "label": 1, "source": "webpage", "category": "spoof"},
        {"id": "tail", "family_id": "c", "label": 1, "source": "webpage", "category": "spoof"},
    ]
    report = summarize_release(cases, [0.8, 0.9, None], threshold=0.5, latencies_ms=[1, 2, 3])
    assert report["status"] == "INCOMPLETE"
    assert report["complete_count"] == 2
    assert report["metrics"] is None
    assert report["incomplete_ids"] == ["tail"]
    assert report["observed_complete_only"]["metrics"]["fp"] == 1
    assert report["observed_complete_only"]["by_source"]["email"]["fp"] == 1


def test_release_report_wilson_and_latency_on_complete_cases():
    cases = [
        {"id": "a", "family_id": "a", "label": 0, "source": "email", "category": "normal"},
        {"id": "b", "family_id": "b", "label": 1, "source": "webpage", "category": "spoof"},
    ]
    report = summarize_release(cases, [0.1, 0.9], threshold=0.5, latencies_ms=[1, 3])
    assert report["status"] == "MEASURED"
    assert report["metrics"]["tp"] == 1
    assert report["metrics"]["tn"] == 1
    assert report["false_positive_rate_wilson_95"][0] == 0
    assert report["latency_ms"]["p95"] == 3
