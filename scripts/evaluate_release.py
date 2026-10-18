"""Evaluate a frozen case set with the verified, local model-only SDK path.

Reports incomplete scans without whole-set accuracy metrics. The output file
must not already exist, avoiding accidental replacement of a recorded run.
"""

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from kjnlae import Guard
from kjnlae.evaluation.external import S_LABS_TEST_SHA256, import_s_labs_test
from kjnlae.evaluation.release_cases import load_cases
from kjnlae.evaluation.release_runner import evaluate_cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--cases", type=Path, help="frozen original JSONL")
    source.add_argument("--s-labs-csv", type=Path, help="pinned external diagnostic TEST CSV")
    parser.add_argument("--sha256", help="precommitted SHA-256 for --cases")
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--model-hash", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.cases and not args.sha256:
        parser.error("--sha256 is required with --cases")
    if args.s_labs_csv and args.sha256:
        parser.error("--s-labs-csv uses its pinned source SHA-256; omit --sha256")
    if args.output.exists() or args.output.is_symlink():
        parser.error("Output already exists; choose a fresh path")
    cases = (
        load_cases(args.cases, args.sha256)
        if args.cases
        else import_s_labs_test(args.s_labs_csv, expected_sha256=S_LABS_TEST_SHA256)
    )
    dataset_sha = args.sha256 if args.cases else S_LABS_TEST_SHA256
    started = time.perf_counter()
    with Guard(model_dir=str(args.model_dir), model_hash=args.model_hash) as guard:
        report = evaluate_cases(guard, cases, threshold=guard.threshold)
    report.update(
        {
            "dataset_sha256": dataset_sha,
            "dataset_kind": "frozen-original" if args.cases else "S-Labs-external-unreviewed",
            "dataset_count_by_label": dict(Counter(str(case.label) for case in cases)),
            "dataset_count_by_source": dict(Counter(case.source for case in cases)),
            "model_manifest_sha256": args.model_hash,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "method": "Guard.scan; model-only ONNX inference; complete inputs only",
            "limitations": (
                "External synthetic examples have unreviewed labels and do not establish "
                "RAG, email, webpage, tool-response or production performance."
                if args.s_labs_csv
                else "Authored fixture metrics apply only to its recorded content families."
            ),
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(
        f"{report['status']}: {report['complete_count']}/{report['count']} complete; {args.output}"
    )
    return 0 if report["status"] == "MEASURED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
