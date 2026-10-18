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
ONNX_TEMPLATE_SHA256 = "78e39b995911d8b3fbf66e0e76ee97e6271e17384b7e80ee994946c75bf06fce"
ONNX_MODEL_SHA256 = "d95dd1850d338f3687f13902869b18e8b6e37f6b23a2dc5845f76133d9dd03a1"
ONNX_MANIFEST_SHA256 = "6b69bd6a790119d4c53fe2df02447114eebcdadddec18d788bf1cf6825ecfa1c"
REVIEWED_THRESHOLD = 0.025134501978754997
V03_CANDIDATE_SOURCE_MANIFEST_SHA256 = (
    "071f6166177efd4af978e46d2f44fae13fe1a4be8c2030c916c3b924ecfe4d61"
)
V03_CANDIDATE_ONNX_MANIFEST_SHA256 = (
    "537899c45553fc6583587684c5685d57c159c1b9f387590b182e1ce0f9a9ea4c"
)
V03_CANDIDATE_ONNX_MODEL_SHA256 = "aee933ab961a49d6c57ce0260220034b3e6e23177fc00602aa4e83578eb2106f"
_ONNX_IDENTITIES: dict[str, dict[str, str | int | float]] = {
    "kjnlae-v0.3.2-onnx-1": {
        "manifest": ONNX_MANIFEST_SHA256,
        "source_manifest": PUBLIC_MODEL_MANIFEST_SHA256,
        "model": ONNX_MODEL_SHA256,
        "steps": 462,
        "threshold": REVIEWED_THRESHOLD,
    },
    "kjnlae-v0.3-candidate-onnx-1": {
        "manifest": V03_CANDIDATE_ONNX_MANIFEST_SHA256,
        "source_manifest": V03_CANDIDATE_SOURCE_MANIFEST_SHA256,
        "model": V03_CANDIDATE_ONNX_MODEL_SHA256,
        "steps": 884,
        "threshold": 0.5,
    },
}
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
    return root / "kjnlae" / "models" / "reviewed-v0.2-onnx"


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

    target = destination or default_model_dir().with_name("reviewed-v0.2")
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
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or not 0 < threshold <= 1
    ):
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


def _assemble_onnx(source: Path, destination: Path) -> None:
    """Fill a weight-free, pinned ONNX graph from the verified safetensors file."""
    import onnx
    from safetensors import safe_open

    template = Path(__file__).with_name("model-template.onnx")
    if _hash(template) != ONNX_TEMPLATE_SHA256:
        raise ValueError("ONNX graph template hash mismatch")
    graph = onnx.load(template, load_external_data=False)
    with safe_open(source / "model.safetensors", framework="np") as tensors:
        names = set(tensors.keys())
        expected = {entry.name.removeprefix("m.") for entry in graph.graph.initializer}
        if names != expected or any(
            not entry.name.startswith("m.") for entry in graph.graph.initializer
        ):
            raise ValueError("ONNX template and model tensors differ")
        for entry in graph.graph.initializer:
            tensor = tensors.get_tensor(entry.name.removeprefix("m."))
            if list(tensor.shape) != list(entry.dims) or str(tensor.dtype) != "float32":
                raise ValueError("ONNX tensor shape or type mismatch")
            entry.raw_data = tensor.tobytes()
    onnx.save(graph, destination)
    if _hash(destination) != ONNX_MODEL_SHA256:
        raise ValueError("ONNX conversion does not match reviewed export")


def verify_onnx_artifact(path: Path, expected_hash: str | None) -> ArtifactManifest:
    """Require a separately pinned ONNX derivative of an evaluated checkpoint."""
    if path.is_symlink() or not path.is_dir():
        raise ValueError("ONNX model directory missing or linked")
    manifest_path = path / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("ONNX manifest missing or linked")
    actual_hash = _hash(manifest_path)
    if expected_hash is not None and actual_hash != expected_hash:
        raise ValueError("ONNX manifest hash does not match deployment pin")
    raw: Any = json.loads(manifest_path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("Unexpected ONNX manifest")
    artifact_version = raw.get("artifact_version")
    if not isinstance(artifact_version, str):
        raise ValueError("Unexpected ONNX manifest")
    identity = _ONNX_IDENTITIES.get(artifact_version)
    if identity is None:
        raise ValueError("Unexpected ONNX manifest")
    if (
        raw.get("source_manifest_sha256") != identity["source_manifest"]
        or raw.get("graph_template_sha256") != ONNX_TEMPLATE_SHA256
        or raw.get("base_revision") != BASE_REVISION
        or raw.get("trained_steps") != identity["steps"]
        or raw.get("quality_status") != "EXPERIMENTAL"
    ):
        raise ValueError("ONNX provenance mismatch")
    threshold = raw.get("threshold")
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or not 0 < threshold <= 1
    ):
        raise ValueError("Invalid ONNX threshold")
    if float(threshold) != identity["threshold"]:
        raise ValueError("ONNX threshold differs from reviewed model")
    if actual_hash != identity["manifest"]:
        raise ValueError("Unreviewed ONNX manifest hash")
    files = raw.get("files")
    required = {"model.onnx", "tokenizer.json", "config.json"}
    if not isinstance(files, dict) or not required.issubset(files):
        raise ValueError("ONNX files missing from manifest")
    for name, expected in files.items():
        if not isinstance(name, str) or not isinstance(expected, str) or name != Path(name).name:
            raise ValueError("Unsafe ONNX manifest entry")
        file_path = path / name
        if file_path.is_symlink() or not file_path.is_file() or _hash(file_path) != expected:
            raise ValueError("ONNX file hash mismatch")
    if files["model.onnx"] != identity["model"]:
        raise ValueError("Unreviewed ONNX graph")
    if any(p.suffix in {".bin", ".pt", ".pkl", ".pickle", ".safetensors"} for p in path.iterdir()):
        raise ValueError("Unexpected weights in ONNX artifact")
    config: Any = json.loads((path / "config.json").read_text())
    if not isinstance(config, dict) or config.get("id2label") != {
        "0": "NON_INJECTION",
        "1": "INJECTION",
    }:
        raise ValueError("Unexpected classifier labels")
    return ArtifactManifest(
        path,
        actual_hash,
        raw["artifact_version"],
        BASE_REVISION,
        int(identity["steps"]),
        float(threshold),
        "EXPERIMENTAL",
    )


def convert_verified_model(source: Path, destination: Path) -> ArtifactManifest:
    """Atomically derive the reviewed CPU graph; leave the source untouched."""
    original = verify_artifact(source, PUBLIC_MODEL_MANIFEST_SHA256)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Model destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(destination.parent).free < 300 * 1024**2:
        raise OSError("At least 300 MiB free disk space is required for ONNX conversion")
    temporary = Path(tempfile.mkdtemp(prefix=".kjnlae-onnx-", dir=destination.parent))
    try:
        for name in (
            "config.json",
            "special_tokens_map.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.txt",
        ):
            shutil.copy2(source / name, temporary / name)
        _assemble_onnx(source, temporary / "model.onnx")
        manifest = {
            "artifact_version": "kjnlae-v0.3.2-onnx-1",
            "source_manifest_sha256": original.sha256,
            "graph_template_sha256": ONNX_TEMPLATE_SHA256,
            "base_revision": original.base_revision,
            "trained_steps": original.trained_steps,
            "quality_status": original.quality_status,
            "threshold": original.threshold,
            "files": {p.name: _hash(p) for p in sorted(temporary.iterdir()) if p.is_file()},
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        result = verify_onnx_artifact(temporary, None)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"Model destination already exists: {destination}")
        temporary.rename(destination)
        return ArtifactManifest(
            destination,
            result.sha256,
            result.artifact_version,
            result.base_revision,
            result.trained_steps,
            result.threshold,
            result.quality_status,
        )
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def download_onnx_model(destination: Path | None = None) -> ArtifactManifest:
    """Explicitly fetch pinned source weights, verify, convert, then discard staging."""
    from huggingface_hub import snapshot_download

    target = destination or default_model_dir()
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"Model destination already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(target.parent).free < 600 * 1024**2:
        raise OSError(
            "At least 600 MiB free disk space is required to download and convert the model"
        )
    temporary = Path(tempfile.mkdtemp(prefix=".kjnlae-download-", dir=target.parent))
    try:
        snapshot_download(
            repo_id=PUBLIC_MODEL_REPO,
            revision=PUBLIC_MODEL_REVISION,
            local_dir=temporary,
            allow_patterns=PUBLIC_MODEL_FILES,
        )
        verify_artifact(temporary, PUBLIC_MODEL_MANIFEST_SHA256)
        return convert_verified_model(temporary, target)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


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
