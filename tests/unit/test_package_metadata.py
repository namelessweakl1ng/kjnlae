"""Ensure plain installation uses the CPU runtime without a training stack."""

from importlib.metadata import requires, version

from kjnlae import __version__


def test_plain_install_declares_inference_dependencies() -> None:
    """A plain install must resolve local inference without CUDA dependencies."""
    declared = requires("kjnlae")
    assert declared is not None
    for name in ("onnxruntime", "onnx", "tokenizers", "safetensors", "huggingface-hub"):
        assert any(
            requirement.lower().startswith(name) and "extra ==" not in requirement.lower()
            for requirement in declared
        ), f"Core dependency missing: {name}"
    for name in ("torch", "transformers", "nvidia", "triton"):
        assert not any(
            requirement.lower().startswith(name) and "extra ==" not in requirement.lower()
            for requirement in declared
        ), f"Training or GPU dependency leaked into core: {name}"


def test_pypi_and_sdk_versions_match() -> None:
    """Keep the wheel metadata and importable SDK version synchronized."""
    assert version("kjnlae") == __version__
