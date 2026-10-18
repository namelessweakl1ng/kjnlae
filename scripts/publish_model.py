"""Stage and explicitly publish only verified kjnlae model files to Hugging Face.

This never uploads source datasets, raw training backups or intermediate checkpoints.
The model repository is PUBLIC once --publish is confirmed.
"""

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from kjnlae.classifiers.artifacts import PUBLIC_MODEL_MANIFEST_SHA256, verify_artifact


def prepare_public_files(model_dir: Path, stage: Path, repo_id: str) -> list[str]:
    """Copy exactly the manifest-listed artifact, manifest, and model card."""
    verify_artifact(model_dir, PUBLIC_MODEL_MANIFEST_SHA256)
    manifest = json.loads((model_dir / "manifest.json").read_text(encoding="utf-8"))
    filenames = ["manifest.json", *sorted(manifest["files"])]
    for name in filenames:
        shutil.copy2(model_dir / name, stage / name)

    card_path = Path(__file__).resolve().parent.parent / "docs" / "model-card-v0.2.md"
    card = card_path.read_text(encoding="utf-8")
    card = card.replace("YOUR_HF_USERNAME/kjnlae-distilbert-v0.2", repo_id)
    (stage / "README.md").write_text(card, encoding="utf-8", newline="\n")
    return [*filenames, "README.md"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--repo-id", help="Hugging Face username/model, if not your default user")
    parser.add_argument(
        "--publish", action="store_true", help="Create a new PUBLIC model repository and upload"
    )
    args = parser.parse_args()

    # The source has already been saved and independently verified on Fedora.
    with tempfile.TemporaryDirectory(prefix="kjnlae-public-model-") as tmpdir:
        staging = Path(tmpdir)
        repo_id = args.repo_id or "YOUR_HF_USERNAME/kjnlae-distilbert-v0.2"
        filenames = prepare_public_files(args.model_dir, staging, repo_id)
        print("Public upload inventory (no training data or backups):")
        for name in filenames:
            file = staging / name
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
            print(f"  {name}: {file.stat().st_size} bytes, sha256={digest}")
        if not args.publish:
            print(
                "Staging verified; NOTHING uploaded. Pass --publish after reviewing the model card."
            )
            return

        try:
            from huggingface_hub import HfApi
        except ImportError as exc:
            raise SystemExit(
                "Install the Hub client first: python -m pip install 'huggingface_hub>=0.30,<1'"
            ) from exc

        api = HfApi()
        if not args.repo_id:
            username = api.whoami()["name"]
            repo_id = f"{username}/kjnlae-distilbert-v0.2"
            (staging / "README.md").write_text(
                (staging / "README.md")
                .read_text(encoding="utf-8")
                .replace("YOUR_HF_USERNAME/kjnlae-distilbert-v0.2", repo_id),
                encoding="utf-8",
                newline="\n",
            )
        print(f"\nAbout to create and publish PUBLIC model https://huggingface.co/{repo_id}")
        print(
            "Proposed weights license: Apache-2.0. Confirm dataset attribution and licensing "
            "before proceeding."
        )
        if input("Type PUBLISH to make the model publicly downloadable: ") != "PUBLISH":
            raise SystemExit("Cancelled. Nothing uploaded.")
        api.create_repo(repo_id=repo_id, repo_type="model", private=False, exist_ok=False)
        api.upload_folder(
            repo_id=repo_id,
            repo_type="model",
            folder_path=str(staging),
            commit_message="Publish experimental kjnlae DistilBERT v0.2 model",
        )
        revision = api.model_info(repo_id).sha
        print(f"\nPUBLIC MODEL: https://huggingface.co/{repo_id}")
        print(f"Hub commit revision: {revision}")
        print(f"Verified manifest SHA-256: {PUBLIC_MODEL_MANIFEST_SHA256}")
        print("Only the listed files were included. Keep all original training archives private.")


if __name__ == "__main__":
    main()
