# Changelog

## 0.3.2 — CPU-only ONNX inference (pending PyPI upload)

- Replaced PyTorch/Transformers in the default install with ONNX Runtime CPU, Tokenizers and a verified weight-free graph template. Training libraries are optional under `[train]`; FastAPI/Uvicorn are optional under `[api]`.
- `kjnlae model download` still verifies the immutable public fine-tuned checkpoint, then derives and verifies a separately identified ONNX artifact. The runtime never downloads or silently falls back.
- Added real PyTorch/ONNX parity measurements, Python 3.11–3.14 Linux inference checks and a clean CPU dependency-resolution audit. Frozen fixtures showed no decision changes; false positives remain a known limitation.
- New default artifact path and manifest pin require running `kjnlae model download` again. The old safetensors directory is retained for research. `model download --repo/--revision/--hash` overrides were removed; see [migration](docs/onnx-runtime.md#migration-from-031).
- The source branch is not a PyPI publication. Windows/macOS real-weight tests and hosted CI for this change remain separate release checks.

## 0.3.1 — default model dependencies (pending PyPI upload)

- `pip install kjnlae` now includes PyTorch, Transformers, Safetensors and Hugging Face Hub dependencies without requiring `[ml]`.
- Updated PyPI-first setup instructions and package-metadata verification tests. Model weight download is still explicit and hash-verified.
- Application and SDK versions are updated to 0.3.1. Python support remains 3.12/3.13; the experimental public v0.2 checkpoint remains unchanged.
- This source release requires a separate PyPI upload to become available to users.


## 0.3.0 — experimental developer-toolkit cleanup (2026-10-14)

- Added a pinned public-model download and verification workflow, per-user model paths, an SDK context manager, and full scored-window/threshold scan results. The model weights and their manifest identity are unchanged.
- Reduced the ordinary CLI to model install/verify, doctor, scan, and serve. Training, benchmarks, and synthetic demos moved to `python -m kjnlae.maintainer_cli`.
- Removed `/v1/*` endpoints and v0.1 action/approval schemas, the duplicate `/v2/guard/input` route, and the dashboard-only lab, evaluation, and history endpoints. SQLite history was removed; content remains out of application logs.
- Replaced the five-tab dashboard with a single accessible scanner showing actual scores, thresholds, windows, and mapped source evidence. No fabricated explanation or token attribution is shown.
- Preserved independent resource/tenant authorization, one-use human approval, guarded execution, RAG ACLs, and output release checks. Missing/corrupt/partial model inspection remains explicitly incomplete.
- Added Windows/macOS no-weight CI checks and platform setup instructions. Actual-weight Windows/macOS inference remains unverified.

This is a breaking change for v0.1 and for clients using removed convenience routes/CLI commands. Use `/v2/scan`, `kjnlae model download`, and the documented maintainer CLI. No automatic migration endpoint or classifier fallback is provided. The model remains experimental and has a 75% benign FPR on the 30-case regression fixture.
