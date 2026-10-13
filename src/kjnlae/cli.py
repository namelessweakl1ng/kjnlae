"""Offline-first model-only CLI. Submitted content is never executed."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from kjnlae import Guard
from kjnlae.classifiers.artifacts import prepare_base_model, verify_artifact
from kjnlae.classifiers.download import REVIEWED_V3_MANIFEST_SHA256, download_verified_model
from kjnlae.evaluation.benchmark import benchmark, markdown_report
from kjnlae.evaluation.model import evaluate_and_promote
from kjnlae.evaluation.sandbox import run_scenarios
from kjnlae.training.dataset import prepare_dataset
from kjnlae.training.fit import FitConfig, fit
from kjnlae.training.probe import ProbeConfig, run_probe


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kjnlae")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan", help="Scan one bounded text with the fine-tuned model")
    scan.add_argument("--text")
    scan.add_argument("--source", default="user")
    scan.add_argument("--mode", help="Retired: v0.2 uses model-only detection")
    batch = commands.add_parser("scan-batch", help="Scan bounded JSONL objects")
    batch.add_argument("--input", type=Path, required=True)
    serve = commands.add_parser("serve", help="Serve API and built frontend")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    bench = commands.add_parser("benchmark", help="Generate measured fixture JSON and Markdown")
    bench.add_argument("--output", type=Path, default=Path("reports/benchmark"))
    bench.add_argument("--dataset", type=Path)
    demo = commands.add_parser("demo", help="Run scripted synthetic authorization scenarios")
    demo.add_argument(
        "--scenario", choices=["baseline", "rag", "hospital", "enterprise"], default="baseline"
    )
    commands.add_parser("doctor", help="Report local artifact and actual inference status")
    commands.add_parser("self-test", help="Run actual model inference on one synthetic sentence")
    model = commands.add_parser("model", help="Manage verified local artifacts")
    models = model.add_subparsers(dest="model_command", required=True)
    verify = models.add_parser("verify")
    verify.add_argument("directory", type=Path)
    verify.add_argument("--hash", required=True)
    download = models.add_parser("download", help="Download and verify public model weights")
    download.add_argument("--repo", required=True, help="Public Hugging Face username/model ID")
    download.add_argument("--revision", default="main", help="Hub commit SHA or revision")
    download.add_argument(
        "--directory", type=Path, default=Path("var/models/full-v0.2-v3-reviewed")
    )
    download.add_argument("--hash", default=REVIEWED_V3_MANIFEST_SHA256)
    base = models.add_parser("prepare-base")
    base.add_argument("directory", type=Path)
    train = commands.add_parser("train", help="Prepare data and run bounded real CPU training")
    trains = train.add_subparsers(dest="train_command", required=True)
    prepare = trains.add_parser("prepare")
    prepare.add_argument("--source", type=Path, action="append", required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--seed", type=int, default=42)
    probe = trains.add_parser("probe")
    probe.add_argument("--base", type=Path, required=True)
    probe.add_argument("--train", type=Path, required=True)
    probe.add_argument("--output", type=Path, required=True)
    fit_cmd = trains.add_parser("fit")
    fit_cmd.add_argument("--base", type=Path, required=True)
    fit_cmd.add_argument("--train", type=Path, required=True)
    fit_cmd.add_argument("--validation", type=Path, required=True)
    fit_cmd.add_argument("--output", type=Path, required=True)
    fit_cmd.add_argument("--epochs", type=int, default=2)
    fit_cmd.add_argument(
        "--deadline", type=int, default=300, help="CPU wall deadline in seconds (max 600)"
    )
    evaluate = trains.add_parser("evaluate")
    evaluate.add_argument("--fit", type=Path, required=True)
    evaluate.add_argument("--prepared", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "kjnlae.api.app:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
            proxy_headers=False,
            access_log=False,
        )
        return
    if args.command == "model":
        if args.model_command == "prepare-base":
            print(prepare_base_model(args.directory))
        elif args.model_command == "download":
            artifact = download_verified_model(
                args.repo, args.directory, revision=args.revision, manifest_sha256=args.hash
            )
            print(json.dumps(artifact.__dict__, default=str, indent=2))
            print(
                "Set KJNLAE_MODEL_DIR to the installed path "
                "and KJNLAE_MODEL_HASH to the pinned hash."
            )
        else:
            print(
                json.dumps(
                    verify_artifact(args.directory, args.hash).__dict__, default=str, indent=2
                )
            )
        return
    if args.command == "train":
        result: Any
        if args.train_command == "prepare":
            result = prepare_dataset(args.source, args.output, args.seed)
        elif args.train_command == "probe":
            result = run_probe(ProbeConfig(args.base, args.train, args.output))
        elif args.train_command == "fit":
            result = fit(
                FitConfig(
                    args.base,
                    args.train,
                    args.validation,
                    args.output,
                    epochs=args.epochs,
                    deadline_s=args.deadline,
                )
            )
        else:
            result = evaluate_and_promote(args.fit, args.prepared)
        print(json.dumps(result, default=lambda x: x.__dict__, indent=2))
        if args.train_command in {"fit", "probe"} and result["status"] == "INCOMPLETE":
            raise SystemExit(1)
        return
    if args.command == "scan" and args.mode is not None:
        parser.error("--mode was removed in v0.2; configure KJNLAE_MODEL_DIR and KJNLAE_MODEL_HASH")
    guard = Guard()
    output: Any
    try:
        if args.command == "scan":
            content = args.text if args.text is not None else sys.stdin.read(32769)
            result = guard.scan(content, source=args.source)
            print(result.model_dump_json(indent=2))
            if result.detection_status == "INCOMPLETE":
                raise SystemExit(1)
        elif args.command == "scan-batch":
            if args.input.stat().st_size > 4 * 1024 * 1024:
                parser.error("JSONL file exceeds 4 MiB")
            incomplete = False
            for line in args.input.read_text().splitlines():
                row = json.loads(line)
                if not isinstance(row, dict) or set(row) - {"text", "source"}:
                    parser.error("JSONL rows must contain only text and source")
                result = guard.scan(**row)
                print(result.model_dump_json())
                incomplete |= result.detection_status == "INCOMPLETE"
            if incomplete:
                raise SystemExit(1)
        elif args.command in {"doctor", "self-test"}:
            result = guard.scan("Please summarize the public schedule.")
            print(
                json.dumps(
                    {"capabilities": guard.capabilities(), "self_test": result.model_dump()},
                    indent=2,
                )
            )
            if result.detection_status == "INCOMPLETE":
                raise SystemExit(1)
        elif args.command == "demo":
            if args.scenario == "baseline":
                output = run_scenarios(guard)
            elif args.scenario == "hospital":
                from kjnlae.integrations.hosts import run_hospital_case

                output = [
                    run_hospital_case(x, guard)
                    for x in ("own_patient", "other_patient", "cross_tenant", "injected_note")
                ]
            elif args.scenario == "enterprise":
                from kjnlae.integrations.hosts import run_enterprise_case

                output = [
                    run_enterprise_case(x, guard)
                    for x in (
                        "public_policy",
                        "hr_authorized",
                        "other_employee",
                        "redirect_email",
                        "detector_miss",
                        "admin_tool",
                    )
                ]
            else:
                from time import time

                from kjnlae.context import TrustedSecurityContext
                from kjnlae.guards.resources import ResourceCatalog, ResourceGrant, ResourceRecord
                from kjnlae.integrations.rag import RagChunk, RagGateway

                catalog = ResourceCatalog((ResourceRecord("public", "demo", "host", 1),))
                grants = (ResourceGrant("demo", "demo", "public", "read_document", 1, time() + 60),)
                retrieved = RagGateway(
                    (
                        RagChunk(
                            "citation-1",
                            "public",
                            "demo",
                            "Policy",
                            "The public policy permits leave.",
                        ),
                    ),
                    guard,
                    catalog,
                ).retrieve("policy", TrustedSecurityContext("demo", "demo", "summarize"), grants)
                output = {"citations": retrieved.citations, "withheld": retrieved.withheld}
            print(json.dumps(output, indent=2))
        elif args.command == "benchmark":
            report = benchmark(guard, args.dataset)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
            args.output.with_suffix(".md").write_text(markdown_report(report))
            print(markdown_report(report))
            if report["detector"]["status"] == "INCOMPLETE":
                raise SystemExit(1)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    finally:
        guard.close()


if __name__ == "__main__":
    main()
