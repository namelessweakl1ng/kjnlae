from pathlib import Path
from runpy import run_path

unexpected_packages = run_path(
    str(Path(__file__).resolve().parents[2] / "scripts/audit_cpu_dependencies.py")
)["unexpected_packages"]


def test_dependency_audit_rejects_gpu_and_training_packages():
    names = ["kjnlae", "onnxruntime", "nvidia-cublas-cu12", "triton", "torch"]
    assert unexpected_packages(names) == ["nvidia-cublas-cu12", "triton", "torch"]


def test_dependency_audit_accepts_cpu_runtime():
    assert unexpected_packages(["kjnlae", "onnxruntime", "onnx", "tokenizers"]) == []
