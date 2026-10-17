"""Ensure the plain PyPI install includes model runtime dependencies."""

from importlib.metadata import requires, version

from kjnlae import __version__


def test_plain_install_declares_inference_dependencies() -> None:
    """A `pip install kjnlae` must not require an optional ML extra."""
    declared = requires("kjnlae")
    assert declared is not None
    for name in ("torch", "transformers", "safetensors", "huggingface-hub"):
        assert any(
            requirement.lower().startswith(name) and "extra ==" not in requirement.lower()
            for requirement in declared
        ), f"Core dependency missing: {name}"


def test_pypi_and_sdk_versions_match() -> None:
    """Keep the wheel metadata and importable SDK version synchronized."""
    assert version("kjnlae") == __version__
