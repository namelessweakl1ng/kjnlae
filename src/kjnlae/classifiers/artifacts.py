"""Local model identity checks; runtime never downloads or loads pickle weights."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BASE_MODEL = "distilbert/distilbert-base-uncased"
BASE_REVISION = "12040accade4e8a0f71eabdb258fecc2e7e948be"
PUBLIC_MODEL_REPO = "namelessweakling/kjnlae-distilbert-v0.2"
PUBLIC_MODEL_REVISION = "d6f5f455a4bc9b2c4587fc7f3011385a871e3653"
PUBLIC_MODEL_MANIFEST_SHA256 = "54e6df56616f4533e1c6a9624f3372ad14bc4d85f5ae97b45c1b3b515a83de9b"
PUBLIC_MODEL_FILES = [
    "manifest.json",
    "config.json",
    "model.safetensors",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
]


def default_model_dir() -> Path:
    """Return a per-user model location without relying on a project checkout."""
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return root / "kjnlae" / "models" / "reviewed-v0.2"


def download_public_model(
    destination: Path | None = None,
    *,
    repository: str = PUBLIC_MODEL_REPO,
    revision: str = PUBLIC_MODEL_REVISION,
    manifest_hash: str = PUBLIC_MODEL_MANIFEST_SHA256,
) -> ArtifactManifest:
    """Download a pinned public snapshot and install only after full hash verification.

    An existing destination is never overwritten. The caller explicitly invokes
    this network operation; inference itself remains offline.
    """
    from huggingface_hub import snapshot_download

    target = destination or default_model_dir()
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"Model destination already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".kjnlae-model-", dir=target.parent))
    try:
        snapshot_download(
            repo_id=repository,
            revision=revision,
            local_dir=temporary,
            allow_patterns=PUBLIC_MODEL_FILES,
        )
        verified = verify_artifact(temporary, manifest_hash)
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"Model destination already exists: {target}")
        shutil.rmtree(temporary / ".cache", ignore_errors=True)
        temporary.rename(target)
        return ArtifactManifest(
            target,
            verified.sha256,
            verified.artifact_version,
            verified.base_revision,
            verified.trained_steps,
            verified.threshold,
            verified.quality_status,
        )
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


@dataclass(frozen=True)
class ArtifactManifest:
    """Verified identity and evaluation metadata for a local trained model."""

    path: Path
    sha256: str
    artifact_version: str
    base_revision: str
    trained_steps: int
    threshold: float
    quality_status: str


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_artifact(path: Path, expected_hash: str | None) -> ArtifactManifest:
    """Verify local model identity, training status, labels and every file digest.

    Raises ValueError for missing, tampered, unevaluated or unsafe artifacts.
    Callers performing inference supply a trusted manifest hash; ``None`` is
    reserved for newly produced training artifacts before a pin is recorded.
    """
    if path.is_symlink() or not path.is_dir():
        raise ValueError("Model directory must be a real local directory")
    manifest_path = path / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("Model manifest missing or linked")
    actual_hash = _hash(manifest_path)
    if expected_hash is not None and actual_hash != expected_hash:
        raise ValueError("Model manifest hash does not match deployment pin")
    raw: Any = json.loads(manifest_path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("Model manifest must be a JSON object")
    if raw.get("base_revision") != BASE_REVISION:
        raise ValueError("Unexpected base model revision")
    if not isinstance(raw.get("trained_steps"), int) or raw["trained_steps"] <= 0:
        raise ValueError("Artifact is not trained")
    if raw.get("evaluated") is not True:
        raise ValueError("Model artifact has not completed evaluation")
    quality_status = raw.get("quality_status")
    if quality_status != "EXPERIMENTAL":
        raise ValueError("Invalid or missing model quality status")
    threshold = raw.get("threshold")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0 < threshold <= 1:
        raise ValueError("Invalid calibration threshold")
    files = raw.get("files")
    if not isinstance(files, dict) or not {
        "model.safetensors",
        "tokenizer.json",
        "config.json",
    }.issubset(files):
        raise ValueError("Required model files missing from manifest")
    for name, expected in files.items():
        if not isinstance(name, str) or not isinstance(expected, str) or name != Path(name).name:
            raise ValueError("Unsafe manifest file entry")
        file_path = path / name
        if file_path.is_symlink() or not file_path.is_file():
            raise ValueError("Model file missing or linked")
        if _hash(file_path) != expected:
            raise ValueError("Model file hash mismatch")
    if any(p.suffix in {".bin", ".pt", ".pkl", ".pickle"} for p in path.iterdir()):
        raise ValueError("Unsafe pickle weights present")
    config: Any = json.loads((path / "config.json").read_text())
    if not isinstance(config, dict):
        raise ValueError("Model config must be a JSON object")
    if config.get("id2label") != {"0": "NON_INJECTION", "1": "INJECTION"}:
        raise ValueError("Unexpected classifier labels")
    return ArtifactManifest(
        path,
        actual_hash,
        str(raw.get("artifact_version", "")),
        BASE_REVISION,
        raw["trained_steps"],
        float(threshold),
        quality_status,
    )


def prepare_base_model(target: Path) -> Path:
    """Explicit online acquisition of the approved base; no runtime fallback."""
    from huggingface_hub import snapshot_download

    target.mkdir(parents=True, exist_ok=True)
    return Path(
        snapshot_download(
            repo_id=BASE_MODEL,
            revision=BASE_REVISION,
            local_dir=target,
            allow_patterns=["config.json", "tokenizer.json", "vocab.txt", "model.safetensors"],
        )
    )
