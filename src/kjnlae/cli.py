"""Small offline-first CLI. Submitted content is never executed."""

import argparse
import json
import sys
from pathlib import Path

from kjnlae import Guard
from kjnlae.api.config import Settings
from kjnlae.classifiers.local import ModelConfig, TransformersClassifier
from kjnlae.evaluation.benchmark import benchmark, markdown_report
from kjnlae.evaluation.sandbox import run_scenarios


def configured_guard() -> Guard:
    cfg = Settings.from_env()
    classifier = (
        TransformersClassifier(ModelConfig(cfg.model_id, cfg.model_revision, cfg.model_label))
        if cfg.model_id
        else None
    )
    return Guard(classifier)


def main() -> None:
    parser = argparse.ArgumentParser(prog="kjnlae")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan", help="Scan text or bounded UTF-8 stdin")
    scan.add_argument("--text")
    scan.add_argument("--source", default="user")
    scan.add_argument("--purpose", default="reference")
    scan.add_argument(
        "--mode", choices=["deterministic", "ml", "combined"], default="deterministic"
    )
    serve = commands.add_parser("serve", help="Serve API and built frontend")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    bench = commands.add_parser("benchmark", help="Generate measured JSON and Markdown reports")
    bench.add_argument("--output", type=Path, default=Path("reports/benchmark"))
    bench.add_argument("--dataset", type=Path)
    commands.add_parser("demo", help="Run six synthetic boundary scenarios")
    importer = commands.add_parser(
        "import-bipia", help="Import locally licensed BIPIA builder JSONL export"
    )
    importer.add_argument("input", type=Path)
    importer.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
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
    if args.command == "import-bipia":
        from kjnlae.evaluation.bipia import import_export

        cases = import_export(args.input)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(cases, indent=2) + "\n")
        print(json.dumps({"imported": len(cases), "output": str(args.output)}))
        return
    guard = configured_guard()
    try:
        if args.command == "scan":
            text = args.text if args.text is not None else sys.stdin.read(32769)
            print(
                guard.scan(
                    text, source=args.source, purpose=args.purpose, mode=args.mode
                ).model_dump_json(indent=2)
            )
        elif args.command == "demo":
            print(json.dumps(run_scenarios(guard), indent=2))
        elif args.command == "benchmark":
            report = benchmark(guard, args.dataset)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
            args.output.with_suffix(".md").write_text(markdown_report(report))
            print(markdown_report(report))
    except ValueError as exc:
        parser.error(str(exc))
    finally:
        if isinstance(guard.classifier, TransformersClassifier):
            guard.classifier.close()


if __name__ == "__main__":
    main()
