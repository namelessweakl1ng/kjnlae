"""Explicit, checksum-pinned acquisition of a public kjnlae model artifact.

No scan or server startup ever calls this downloader.
"""

import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path

from kjnlae.classifiers.artifacts import ArtifactManifest, verify_artifact

REVIEWED_V3_MANIFEST_SHA256 = "54e6df56616f4533e1c6a9624f3372ad14bc4d85f5ae97b45c1b3b515a83de9b"
_REPO_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:json|txt|safetensors)\Z")
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")


def download_verified_model(
    repo_id: str,
    destination: Path,
    *,
    revision: str = "main",
    manifest_sha256: str = REVIEWED_V3_MANIFEST_SHA256,
) -> ArtifactManifest:
    """Download only a pinned public artifact, verify it, then atomically install it.

    The destination must not already exist; an incomplete or changed download
    must never replace an existing installation.
    """
    if not _REPO_ID.fullmatch(repo_id):
        raise ValueError("Expected a Hugging Face model ID like 'username/model'")
    if not revision or revision.startswith("/") or ".." in revision:
        raise ValueError("Invalid model revision")
    if not _SHA256.fullmatch(manifest_sha256):
        raise ValueError("A lowercase 64-character model manifest SHA-256 is required")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination already exists; choose a new directory")

    try:
        from huggingface_hub import hf_hub_download, snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "Install the optional Hub client: python -m pip install 'huggingface_hub>=0.30,<1'"
        ) from exc

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".kjnlae-model-", dir=destination.parent))
    try:
        manifest_path = Path(
            hf_hub_download(
                repo_id=repo_id,
                filename="manifest.json",
                revision=revision,
                local_dir=staging,
                token=False,
            )
        )
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise ValueError("Missing or linked public model manifest")
        if manifest_path.stat().st_size > 1024 * 1024:
            raise ValueError("Model manifest is too large")
        actual_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        if actual_sha != manifest_sha256:
            raise ValueError("Public model manifest does not match expected SHA-256")
        manifest = json.loads(manifest_path.read_text())
        files = manifest.get("files")
        if not isinstance(files, dict) or not 1 <= len(files) <= 32:
            raise ValueError("Invalid model manifest file inventory")
        if any(
            not isinstance(name, str)
            or not _FILENAME.fullmatch(name)
            or not isinstance(digest, str)
            or not _SHA256.fullmatch(digest)
            for name, digest in files.items()
        ):
            raise ValueError("Unsafe or malformed model manifest file entry")

        snapshot_download(
            repo_id=repo_id,
            revision=revision,
            local_dir=staging,
            allow_patterns=["manifest.json", *files],
            token=False,
        )
        artifact = verify_artifact(staging, manifest_sha256)
        # Local-dir HF caches are not part of the model artifact.
        shutil.rmtree(staging / ".cache", ignore_errors=True)
        if destination.exists() or destination.is_symlink():
            raise ValueError("Destination appeared while downloading")
        staging.rename(destination)
        return ArtifactManifest(
            path=destination,
            sha256=artifact.sha256,
            artifact_version=artifact.artifact_version,
            base_revision=artifact.base_revision,
            trained_steps=artifact.trained_steps,
            threshold=artifact.threshold,
            quality_status=artifact.quality_status,
        )
    finally:
        if staging.exists():
            shutil.rmtree(staging)
