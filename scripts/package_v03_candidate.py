"""Package a gated local safetensors candidate and its separate ONNX derivative."""

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from kjnlae.classifiers.artifacts import (
    BASE_REVISION,
    ONNX_TEMPLATE_SHA256,
    PUBLIC_MODEL_MANIFEST_SHA256,
    verify_artifact,
)
from kjnlae.evaluation.v03_gate import check_pre_export_gate

TOKENIZER_FILES = (
    "config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_manifest(path: Path, value: dict[str, Any]) -> str:
    target = path / "manifest.json"
    target.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return _sha(target)


def _fill_onnx(template: Path, weights: Path, output: Path) -> str:
    import onnx
    from safetensors import safe_open

    if _sha(template) != ONNX_TEMPLATE_SHA256:
        raise ValueError("Pinned weight-free ONNX template changed")
    graph = onnx.load(template, load_external_data=False)
    with safe_open(weights, framework="np") as tensors:
        expected = {item.name.removeprefix("m.") for item in graph.graph.initializer}
        if set(tensors.keys()) != expected or any(
            not item.name.startswith("m.") for item in graph.graph.initializer
        ):
            raise ValueError("ONNX tensor names differ from candidate weights")
        for item in graph.graph.initializer:
            value = tensors.get_tensor(item.name.removeprefix("m."))
            if list(value.shape) != list(item.dims) or str(value.dtype) != "float32":
                raise ValueError("ONNX tensor shape/type mismatch")
            item.raw_data = value.tobytes()
    onnx.checker.check_model(graph)
    onnx.save(graph, output)
    return _sha(output)


def _verify_local_onnx(path: Path, expected_manifest: str, expected_model: str) -> None:
    if path.is_symlink() or not path.is_dir() or _sha(path / "manifest.json") != expected_manifest:
        raise ValueError("Candidate ONNX manifest mismatch")
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if (
        manifest["artifact_version"] != "kjnlae-v0.3-candidate-onnx-1"
        or manifest["graph_template_sha256"] != ONNX_TEMPLATE_SHA256
        or manifest["files"]["model.onnx"] != expected_model
    ):
        raise ValueError("Candidate ONNX identity mismatch")
    for name, digest in manifest["files"].items():
        file = path / name
        if name != file.name or file.is_symlink() or not file.is_file() or _sha(file) != digest:
            raise ValueError("Candidate ONNX file checksum mismatch")
    if any(file.suffix in {".safetensors", ".bin", ".pt", ".pkl"} for file in path.iterdir()):
        raise ValueError("Candidate ONNX directory contains unsafe weights")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", required=True, type=Path)
    parser.add_argument("--fit", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--final", required=True, type=Path)
    parser.add_argument("--original-output", required=True, type=Path)
    parser.add_argument("--onnx-output", required=True, type=Path)
    args = parser.parse_args()
    if args.original_output.exists() or args.onnx_output.exists():
        raise FileExistsError("Candidate outputs must not already exist")
    control = verify_artifact(args.control, PUBLIC_MODEL_MANIFEST_SHA256)
    fit = json.loads((args.fit / "fit-report.json").read_text(encoding="utf-8"))
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    final = json.loads(args.final.read_text(encoding="utf-8"))
    best = args.fit / "best"
    candidate_hash = _sha(best / "model.safetensors")
    if (
        fit.get("status") != "COMPLETE"
        or fit.get("best_weight_sha256") != candidate_hash
        or selection.get("status") != "SELECTED"
        or selection.get("candidate_weight_sha256") != candidate_hash
        or final.get("status") != "MEASURED"
        or final.get("candidate_weight_sha256") != candidate_hash
        or final.get("selection_sha256") != _sha(args.selection)
        or final["candidate"]["threshold"] != selection["threshold"]
    ):
        raise ValueError("Candidate training, selection, or final evaluation is incomplete")
    failures = check_pre_export_gate(final)
    if failures:
        raise ValueError("Pre-export release gate failed: " + "; ".join(failures))
    template = Path(__file__).resolve().parents[1] / "src/kjnlae/classifiers/model-template.onnx"
    args.original_output.parent.mkdir(parents=True, exist_ok=True)
    args.onnx_output.parent.mkdir(parents=True, exist_ok=True)
    original = Path(tempfile.mkdtemp(prefix=".v03-original-", dir=args.original_output.parent))
    onnx_dir = Path(tempfile.mkdtemp(prefix=".v03-onnx-", dir=args.onnx_output.parent))
    try:
        for name in (*TOKENIZER_FILES, "model.safetensors"):
            shutil.copy2(best / name, original / name)
        source_manifest = {
            "artifact_version": "kjnlae-v0.3-candidate-local-1",
            "base_revision": BASE_REVISION,
            "parent_model_manifest_sha256": control.sha256,
            "parent_weight_sha256": _sha(args.control / "model.safetensors"),
            "best_epoch": fit["best_epoch"],
            "trained_steps": fit["best_epoch"]
            * (
                (fit["train_count"] + fit["config"]["batch_size"] - 1)
                // fit["config"]["batch_size"]
            ),
            "total_optimizer_steps": fit["steps"],
            "train_sha256": fit["train_sha256"],
            "validation_sha256": fit["validation_sha256"],
            "calibration_sha256": selection["calibration_sha256"],
            "selection_sha256": _sha(args.selection),
            "final_evaluation_sha256": _sha(args.final),
            "threshold": selection["threshold"],
            "quality_status": "EXPERIMENTAL",
            "evaluated": True,
            "files": {file.name: _sha(file) for file in sorted(original.iterdir())},
        }
        original_manifest = _write_manifest(original, source_manifest)
        verify_artifact(original, original_manifest)
        for name in TOKENIZER_FILES:
            shutil.copy2(original / name, onnx_dir / name)
        model_hash = _fill_onnx(template, original / "model.safetensors", onnx_dir / "model.onnx")
        onnx_manifest = {
            "artifact_version": "kjnlae-v0.3-candidate-onnx-1",
            "source_manifest_sha256": original_manifest,
            "graph_template_sha256": ONNX_TEMPLATE_SHA256,
            "base_revision": BASE_REVISION,
            "trained_steps": source_manifest["trained_steps"],
            "quality_status": "EXPERIMENTAL",
            "threshold": selection["threshold"],
            "files": {file.name: _sha(file) for file in sorted(onnx_dir.iterdir())},
        }
        onnx_manifest_hash = _write_manifest(onnx_dir, onnx_manifest)
        _verify_local_onnx(onnx_dir, onnx_manifest_hash, model_hash)
        original.rename(args.original_output)
        onnx_dir.rename(args.onnx_output)
        print(
            json.dumps(
                {
                    "original_manifest_sha256": original_manifest,
                    "weight_sha256": candidate_hash,
                    "onnx_manifest_sha256": onnx_manifest_hash,
                    "onnx_model_sha256": model_hash,
                    "template_sha256": ONNX_TEMPLATE_SHA256,
                },
                indent=2,
            )
        )
    finally:
        if original.exists():
            shutil.rmtree(original)
        if onnx_dir.exists():
            shutil.rmtree(onnx_dir)


if __name__ == "__main__":
    main()
