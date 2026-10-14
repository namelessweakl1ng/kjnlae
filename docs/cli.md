# CLI

The ordinary `kjnlae` entry point has five operations:

| Command | Result |
|---|---|
| `kjnlae model download [--directory PATH]` | Explicitly download the reviewed public model at a pinned commit, verify manifest and all files, and install without overwriting. Advanced use may supply `--repo`, `--revision`, and `--hash` together. |
| `kjnlae model verify [--directory PATH] [--hash SHA256]` | Recheck a local artifact; defaults to the reviewed model and pin. |
| `kjnlae doctor` | Show capability status and perform an actual local inference self-test. |
| `kjnlae scan [--text TEXT] [--source SOURCE]` | Inspect bounded text; without `--text`, read at most 32,769 characters from standard input. Exit 1 on `INCOMPLETE`, 2 on invalid usage. |
| `kjnlae serve [--host HOST] [--port PORT]` | Start FastAPI and the built dashboard, loopback by default. |

A first model download is online and does not need a Hugging Face token. Inference is offline. Missing or corrupt weights never trigger a classifier fallback. Do not place real secrets in `--text`, which shell history/process listings may retain; use standard input or the SDK.

Maintainer-only operations use `python -m kjnlae.maintainer_cli prepare-base|train|benchmark|demo`. They are not part of the everyday command tree. Run `python -m kjnlae.maintainer_cli --help` for arguments and see [training](model-training.md) and [benchmarks](benchmarks.md).
