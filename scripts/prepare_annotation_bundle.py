"""Prepare a private, blinded v0.4 candidate bundle from pinned external sources.

Requires the optional training environment with pyarrow installed. Never commit the output.
"""

import argparse
import hashlib
import json
from pathlib import Path

import pyarrow.parquet as parquet

from kjnlae.evaluation.annotation import (
    agentdojo_candidates,
    build_review_bundle,
    import_bipia_file,
    neuralchemy_candidates,
    verify_git_checkout,
)

AGENTDOJO_REVISION = "089ed468cf3ed0322acc66b0211f26d9d90dbf60"
BIPIA_REVISION = "a004b69ec0dd446e0afd461d98cb5e96e120a5d0"
NEURALCHEMY_REVISION = "7d70432dfcf47a821612cbf9d34e9d9e3ad20e75"
NEURALCHEMY_SHA256 = "fb5432035fdd8453d61f6593bfe78ee2970403c5ea59959b642a6708e2bef670"
BIPIA_FILES = {
    "email": (
        "email/test.jsonl",
        "217b403faaa1d0cb12c24892bea39f4a0b9e2819919ac7e2b902006e28278cdb",
        "email",
    ),
    "code": (
        "code/test.jsonl",
        "ed40b84f541352fb45753032a80750922de8d5e0b70997924df3d04cf942e058",
        "retrieved_document",
    ),
    "table": (
        "table/test.jsonl",
        "3d5eaab192b80bada762e3cd7655583a14e5888ba8b845a01f0434e4ccc4291e",
        "retrieved_document",
    ),
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agentdojo-checkout", type=Path, required=True)
    parser.add_argument("--bipia-checkout", type=Path, required=True)
    parser.add_argument("--neuralchemy-test", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repository = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if output == repository or repository in output.parents:
        parser.error("The private annotation bundle must be written outside the Git repository")
    if output.exists() or output.with_name(output.name + "-reviewer").exists():
        parser.error("The annotation output already exists")
    verify_git_checkout(args.agentdojo_checkout, AGENTDOJO_REVISION)
    verify_git_checkout(args.bipia_checkout, BIPIA_REVISION)
    neuralchemy = args.neuralchemy_test
    if (
        neuralchemy.is_symlink()
        or not neuralchemy.is_file()
        or neuralchemy.stat().st_size > 4 * 1024 * 1024
    ):
        parser.error("NeurAlchemy test parquet is missing, linked, or oversized")
    if file_sha256(neuralchemy) != NEURALCHEMY_SHA256:
        parser.error("NeurAlchemy test parquet SHA-256 mismatch")

    stats: dict[str, int | str] = {}
    candidates = agentdojo_candidates(
        args.agentdojo_checkout / "runs", stats=stats, expected_revision=AGENTDOJO_REVISION
    )
    for relative, digest, source in BIPIA_FILES.values():
        candidates.extend(
            import_bipia_file(
                args.bipia_checkout / "benchmark" / relative,
                source=source,
                expected_sha256=digest,
            )
        )
    table = parquet.read_table(neuralchemy)
    if not 1 <= table.num_rows <= 10000:
        parser.error("NeurAlchemy test row count outside supported bounds")
    candidates.extend(neuralchemy_candidates(table.to_pylist(), source_digest=NEURALCHEMY_SHA256))
    metadata = {
        "agentdojo": {
            "revision": AGENTDOJO_REVISION,
            "license": "MIT repository; review individual content before redistribution",
            "import": stats,
        },
        "bipia": {
            "revision": BIPIA_REVISION,
            "file_sha256": {name: row[1] for name, row in BIPIA_FILES.items()},
            "license": "Repository MIT/NOTICE; dataset-specific obligations require review",
        },
        "neuralchemy": {
            "revision": NEURALCHEMY_REVISION,
            "file_sha256": NEURALCHEMY_SHA256,
            "license": (
                "Dataset card says Apache-2.0, but component sources include research-use "
                "material; private review only"
            ),
        },
    }
    manifest = build_review_bundle(candidates, output, source_metadata=metadata)
    print(
        json.dumps(
            {
                "sealed_output": str(output),
                "reviewer_output": str(output.with_name(output.name + "-reviewer")),
                "candidate_count": manifest["candidate_count"],
                "review_sha256": manifest["review_sha256"],
                "sealed_provenance_sha256": manifest["sealed_provenance_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
