# CLI

The ordinary `kjnlae` entry point has five operations:

| Command | Result |
|---|---|
| `kjnlae model download [--directory PATH]` | Explicitly fetch the pinned public checkpoint, verify it, derive the separately hashed ONNX CPU artifact, and install without overwriting. Repository, revision and hash overrides are intentionally unavailable for this command. |
| `kjnlae model verify [--directory PATH] [--hash SHA256]` | Recheck a local ONNX artifact; defaults to the reviewed derived-model pin. |
| `kjnlae doctor` | Show capability status and perform an actual local inference self-test. |
| `kjnlae scan [--text TEXT] [--source SOURCE]` | Inspect bounded text; without `--text`, read at most 32,769 characters from standard input. Exit 1 on `INCOMPLETE`, 2 on invalid usage. |
| `kjnlae serve [--host HOST] [--port PORT]` | Start FastAPI after installing `[api]`, loopback by default. The dashboard is available from a source checkout with built assets or the Docker image; a standalone wheel serves the API only. |

A first model download is online and does not need a Hugging Face token. Inference is offline. Missing or corrupt weights never trigger a classifier fallback. Do not place real secrets in `--text`, which shell history/process listings may retain; use standard input or the SDK. These commands require kjnlae 0.3.2 or later. Check [PyPI](https://pypi.org/project/kjnlae/) before installing without a version constraint; 0.3.0 uses the older runtime.

Maintainer-only operations use `python -m kjnlae.maintainer_cli prepare-base|train|benchmark|demo`. They are not part of the everyday command tree. Run `python -m kjnlae.maintainer_cli --help` for arguments and see [training](model-training.md) and [benchmarks](benchmarks.md).
