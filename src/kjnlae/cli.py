"""Small developer CLI; training and benchmarks live in maintainer_cli."""

import argparse
import json
import sys
from pathlib import Path

from kjnlae import Guard
from kjnlae.classifiers.artifacts import (
    PUBLIC_MODEL_MANIFEST_SHA256,
    PUBLIC_MODEL_REPO,
    PUBLIC_MODEL_REVISION,
    default_model_dir,
    download_public_model,
    verify_artifact,
)

SOURCES = ("user", "retrieved_document", "webpage", "email", "attachment", "tool_response", "agent")


def _parser() -> argparse.ArgumentParser:
    """Define only operations needed to install, diagnose, scan, or serve."""
    parser = argparse.ArgumentParser(prog="kjnlae")
    commands = parser.add_subparsers(dest="command", required=True)
    model = commands.add_parser("model", help="Install or verify the reviewed local model")
    models = model.add_subparsers(dest="model_command", required=True)
    download = models.add_parser("download", help="Download and verify a pinned model snapshot")
    download.add_argument("--directory", type=Path, default=default_model_dir())
    download.add_argument("--repo", default=PUBLIC_MODEL_REPO)
    download.add_argument("--revision", default=PUBLIC_MODEL_REVISION)
    download.add_argument("--hash", default=PUBLIC_MODEL_MANIFEST_SHA256)
    verify = models.add_parser("verify", help="Verify installed model files against a manifest pin")
    verify.add_argument("--directory", type=Path, default=default_model_dir())
    verify.add_argument("--hash", default=PUBLIC_MODEL_MANIFEST_SHA256)
    commands.add_parser("doctor", help="Verify model identity and run real local inference")
    scan = commands.add_parser("scan", help="Inspect one bounded text")
    scan.add_argument("--text", help="Text to inspect; otherwise read UTF-8 standard input")
    scan.add_argument("--source", choices=SOURCES, default="user")
    serve = commands.add_parser("serve", help="Serve the API and built dashboard")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run the requested command; incomplete inspection exits nonzero."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "model":
            if args.model_command == "download":
                artifact = download_public_model(
                    args.directory,
                    repository=args.repo,
                    revision=args.revision,
                    manifest_hash=args.hash,
                )
            else:
                artifact = verify_artifact(args.directory, args.hash)
            print(
                json.dumps(
                    {
                        "directory": str(artifact.path),
                        "manifest_sha256": artifact.sha256,
                        "threshold": artifact.threshold,
                        "quality_status": artifact.quality_status,
                    },
                    indent=2,
                )
            )
            return
        if args.command == "serve":
            import uvicorn

            uvicorn.run(
                "kjnlae.api.app:create_app",
                factory=True,
                host=args.host,
                port=args.port,
                proxy_headers=False,
                access_log=False,
            )
            return
        with Guard() as guard:
            if args.command == "doctor":
                result = guard.scan("Please summarize the public schedule.")
                print(
                    json.dumps(
                        {"capabilities": guard.capabilities(), "self_test": result.model_dump()},
                        indent=2,
                    )
                )
            else:
                content = args.text if args.text is not None else sys.stdin.read(32769)
                result = guard.scan(content, source=args.source)
                print(result.model_dump_json(indent=2))
            if result.detection_status == "INCOMPLETE":
                print(
                    "Model inspection incomplete. Run `kjnlae model download` "
                    "then `kjnlae doctor`.",
                    file=sys.stderr,
                )
                raise SystemExit(1)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
