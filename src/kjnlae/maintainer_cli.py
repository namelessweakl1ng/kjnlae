"""Development-only training, evaluation, and synthetic sandbox commands."""

import argparse
import json
from pathlib import Path
from typing import Any

from kjnlae import Guard
from kjnlae.classifiers.artifacts import prepare_base_model
from kjnlae.evaluation.benchmark import benchmark, markdown_report
from kjnlae.evaluation.model import evaluate_and_promote
from kjnlae.evaluation.sandbox import run_scenarios
from kjnlae.training.dataset import prepare_dataset
from kjnlae.training.fit import FitConfig, fit
from kjnlae.training.probe import ProbeConfig, run_probe


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m kjnlae.maintainer_cli")
    commands = parser.add_subparsers(dest="command", required=True)
    base = commands.add_parser("prepare-base", help="Download pinned base model for training")
    base.add_argument("directory", type=Path)
    bench = commands.add_parser("benchmark", help="Measure fixture detection and sandbox outcomes")
    bench.add_argument("--output", type=Path, default=Path("reports/benchmark"))
    bench.add_argument("--dataset", type=Path)
    demo = commands.add_parser("demo", help="Run synthetic local authorization scenarios")
    demo.add_argument(
        "--scenario", choices=["baseline", "rag", "hospital", "enterprise"], default="baseline"
    )
    train = commands.add_parser("train", help="Prepare data and run bounded CPU training")
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
    fit_cmd.add_argument("--deadline", type=int, default=300)
    evaluate = trains.add_parser("evaluate")
    evaluate.add_argument("--fit", type=Path, required=True)
    evaluate.add_argument("--prepared", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run reproducibility commands outside the user-facing runtime CLI."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare-base":
            print(prepare_base_model(args.directory))
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
        with Guard() as guard:
            if args.command == "benchmark":
                report = benchmark(guard, args.dataset)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
                args.output.with_suffix(".md").write_text(markdown_report(report))
                print(markdown_report(report))
                if report["detector"]["status"] == "INCOMPLETE":
                    raise SystemExit(1)
            else:
                output: Any
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
                    from kjnlae.guards.resources import (
                        ResourceCatalog,
                        ResourceGrant,
                        ResourceRecord,
                    )
                    from kjnlae.integrations.rag import RagChunk, RagGateway

                    catalog = ResourceCatalog((ResourceRecord("public", "demo", "host", 1),))
                    grants = (
                        ResourceGrant("demo", "demo", "public", "read_document", 1, time() + 60),
                    )
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
                    ).retrieve(
                        "policy", TrustedSecurityContext("demo", "demo", "summarize"), grants
                    )
                    output = {"citations": retrieved.citations, "withheld": retrieved.withheld}
                print(json.dumps(output, indent=2))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
