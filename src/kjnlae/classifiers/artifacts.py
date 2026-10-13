"""Local model identity checks; runtime never downloads or loads pickle weights."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BASE_MODEL = "distilbert/distilbert-base-uncased"
BASE_REVISION = "12040accade4e8a0f71eabdb258fecc2e7e948be"


@dataclass(frozen=True)
class ArtifactManifest:
    path: Path
    sha256: str
    artifact_version: str
    base_revision: str
    trained_steps: int
    threshold: float
    approved: bool


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_artifact(path: Path, expected_hash: str | None) -> ArtifactManifest:
    if path.is_symlink() or not path.is_dir():
        raise ValueError("Model directory must be a real local directory")
    manifest_path = path / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("Model manifest missing or linked")
    actual_hash = _hash(manifest_path)
    if expected_hash is not None and actual_hash != expected_hash:
        raise ValueError("Model manifest hash does not match deployment pin")
    raw: dict[str, Any] = json.loads(manifest_path.read_text())
    if raw.get("base_revision") != BASE_REVISION:
        raise ValueError("Unexpected base model revision")
    if not isinstance(raw.get("trained_steps"), int) or raw["trained_steps"] <= 0:
        raise ValueError("Artifact is not trained")
    if not raw.get("approved"):
        raise ValueError("Model artifact has not passed promotion")
    threshold = raw.get("threshold")
    if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
        raise ValueError("Invalid calibration threshold")
    files = raw.get("files")
    if not isinstance(files, dict) or not {
        "model.safetensors", "tokenizer.json", "config.json"
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
    config = json.loads((path / "config.json").read_text())
    if config.get("id2label") != {"0": "NON_INJECTION", "1": "INJECTION"}:
        raise ValueError("Unexpected classifier labels")
    return ArtifactManifest(
        path, actual_hash, str(raw.get("artifact_version", "")), BASE_REVISION,
        raw["trained_steps"], float(threshold), True,
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
