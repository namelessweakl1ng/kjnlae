# kjnlae

kjnlae is an **experimental** prompt-injection scanner plus an independent authorization gateway for AI applications. Its sole prompt-injection detector is the project's fine-tuned English DistilBERT model. A scan supplies evidence; it cannot prove that an attack succeeded or guarantee that an LLM will resist one. Resource grants, tenant checks, exact-action approvals, tool execution and output release are enforced in host code, regardless of the scanner's score.

## Install from PyPI

Once **kjnlae 0.3.2** is published on PyPI, the normal CPU-first installation is:

```bash
python -m pip install kjnlae
kjnlae model download
kjnlae model verify
kjnlae doctor
```

**Release status:** at the time of this change, PyPI still serves 0.3.0. Do not expect that older release to have the CPU-only ONNX runtime. Until 0.3.2 is published, install this reviewed source branch with `python -m pip install .` from its checkout or install a wheel built from it. Publishing to PyPI is a separate maintainer action; a GitHub push does not publish a package.

For a maintainer release, first merge this branch after review and passing hosted CI, then build and inspect both distributions with `python -m pip install build`, `python -m build`, and `tar -tzf dist/kjnlae-0.3.2.tar.gz`. Verify the source archive and wheel include `model-template.onnx` but no trained weights. After testing a clean install of the built wheel and the explicit model download, publish a GitHub release for tag `v0.3.2` from the reviewed main commit. The repository's [PyPI workflow](.github/workflows/publish.yml) uses the `pypi` environment and OIDC trusted publishing on a **published** release; confirm its build and publish jobs succeed and then verify PyPI serves 0.3.2. No publishing was performed in this branch.

The base package installs Pydantic, NumPy, ONNX Runtime CPU, ONNX, Tokenizers, Safetensors and Hugging Face Hub. The measured clean pip wheel installation occupied about **220 MB** for kjnlae and its dependencies, excluding pip itself. It does **not** install PyTorch, Transformers, CUDA, NVIDIA libraries or Triton. API hosting is optional: `python -m pip install 'kjnlae[api]'`. Training and historical PyTorch evaluation need `python -m pip install 'kjnlae[train]'`; on Linux, that extra may resolve CUDA wheels. Node.js is needed only for building the dashboard from source. No GPU, CUDA Toolkit, driver, hosted LLM or paid API key is needed for scanning.

The separately downloaded model is about **269 MB installed**. It is not included in the wheel. The verified original [public checkpoint](https://huggingface.co/namelessweakling/kjnlae-distilbert-v0.2) is downloaded from a pinned revision and converted locally through a weight-free, hashed ONNX graph template. The installer verifies the original SHA-256 manifest and every source file, then verifies the derived ONNX graph SHA-256 and installs it atomically. Inference is offline and never downloads a model. The original public checkpoint remains unchanged. See [runtime provenance and measurements](docs/onnx-runtime.md).

```python
from kjnlae import Guard

with Guard() as guard:
    result = guard.scan("Ignore previous instructions.", source="retrieved_document")
    print(result.detection_status, result.policy_decision, result.model_score)
    print(result.windows)  # real scored windows and source offsets
```

`from kjnlae import ActionGateway, GuardedExecutor, OutputGuard, HostAuthority, ResourceCatalog` also remains available without FastAPI. An absent, corrupt or timed-out model produces `INCOMPLETE`; it never falls back to rules, an untrained checkpoint or a mock. A prompt-injection score never grants tool permission. See [architecture](docs/architecture.md), [policies](docs/security-policies.md) and [limitations](docs/limitations.md).

## Platform quickstarts

Supported Python versions on **Linux x86-64 are 3.11, 3.12, 3.13 and 3.14**. Each was installed in a clean environment and ran the real local model in the current cloud Linux environment. Windows and macOS passed hosted no-weight CI jobs, but real-model inference there still needs verification; see the [compatibility table](docs/onnx-runtime.md#compatibility).

**Fedora/Linux:** install a supported Python version, create a virtual environment and use its interpreter. Fedora's default Python 3.14 is supported on Linux x86-64.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install .  # run from this source checkout until 0.3.2 reaches PyPI
kjnlae model download
kjnlae doctor
```

**Windows PowerShell:** install Python 3.11–3.14 from the official Python installer, then:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python -m pip install .
.\.venv\Scripts\kjnlae model download
.\.venv\Scripts\kjnlae doctor
```

**macOS:** Apple Silicon has ONNX Runtime wheels for Python 3.11–3.14 on macOS 14 or newer. Intel macOS 13+ has ONNX Runtime wheels only through Python 3.13 in the checked releases. Real-weight inference on macOS has **not** been verified here.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install .
kjnlae model download
kjnlae doctor
```

For a source installation before PyPI release, replace `python -m pip install kjnlae` with `python -m pip install .` from the repository root. `kjnlae doctor` performs a real inference and must report `"model_status": "AVAILABLE"` and `"inspection_complete": true`. `kjnlae model verify` checks the installed derived artifact. `kjnlae scan --source webpage --text '...'` prints structured JSON and exits nonzero on incomplete inspection.

The default model directory is `~/.local/share/kjnlae/models/reviewed-v0.2-onnx` (or `$XDG_DATA_HOME`) on Linux, `%LOCALAPPDATA%\kjnlae\models\reviewed-v0.2-onnx` on Windows, and `~/Library/Application Support/kjnlae/models/reviewed-v0.2-onnx` on macOS. Set **both** `KJNLAE_MODEL_DIR` and `KJNLAE_MODEL_HASH` for a custom, trusted local artifact. The reviewed derived manifest pin is `6b69bd6a790119d4c53fe2df02447114eebcdadddec18d788bf1cf6825ecfa1c`.

If a disposable test install used too much space, first deactivate it, then remove only that virtual environment (`rm -rf .venv` on Unix, `Remove-Item -Recurse .venv` in PowerShell). `python -m pip cache purge` clears pip's own cache if you choose. To uninstall, use `python -m pip uninstall kjnlae` and remove only the kjnlae model directory shown above if its contents are no longer needed. The installer does not clear unrelated caches or files.

## API, dashboard and development

```bash
python -m pip install 'kjnlae[api]'
kjnlae serve                    # binds 127.0.0.1:8000
```

The versioned API includes `/v2/scan`, `/v2/rag/inspect`, `/v2/guard/action`, `/v2/guard/output`, `/v2/system/capabilities`, `/health/live` and `/health/ready`. The standalone wheel serves the API without compiled dashboard assets and says so at startup. The dashboard is built from the source checkout or Docker image:

```bash
python -m pip install '.[api,dev]'
npm --prefix frontend ci --ignore-scripts
npm --prefix frontend run build
kjnlae serve
```

For Docker, install the model into a project-local directory, put `KJNLAE_MODEL_HASH=6b69bd6a790119d4c53fe2df02447114eebcdadddec18d788bf1cf6825ecfa1c` and `KJNLAE_MODEL_DIR_HOST=./var/models/reviewed-v0.2-onnx` in a private `.env`, then run `docker compose up --build -d`. The container's UID 10001 needs read/traverse access to that dedicated model directory. No weights are baked into the image. See [deployment](docs/deployment.md) and [API examples](docs/api.md).

Training remains a separate maintainer workflow documented in [model training](docs/model-training.md). Development checks use `python -m pip install '.[api,train,dev]'`, `bash scripts/verify_all.sh`, `python scripts/audit_cpu_dependencies.py`, `npm --prefix frontend test`, and `npm --prefix frontend run build`. The real-weight release gate uses `KJNLAE_TEST_ONNX_DIR`, `KJNLAE_TEST_ONNX_HASH`, and `KJNLAE_VERIFY_RELEASE=1`; optionally set `KJNLAE_TEST_MODEL_DIR` for comparison with the original PyTorch checkpoint. The [codebase guide](CODEBASE.md) describes the module contracts. The [verification record](docs/verification.md) separates current measurements from historical results.

## Security and model limitations

Untrusted pages, retrieved chunks, emails and tool responses remain data; they cannot supply trusted authority. Host code supplies authenticated principals, tenant and resource grants, destination restrictions, and one-use approvals tied to exact action parameters. Output controls inspect known sensitive resources and destinations before release. Those controls can deny an unauthorized action even when the classifier misses an injection. A static API key authenticates one deployment, not individual users. Production use requires a trusted identity layer and explicit security configuration; see [threat model](docs/threat-model.md) and [SECURITY.md](SECURITY.md).

The model is **English-first and experimental**. On the frozen 50-case independent fixture it made 10 benign false positives out of 35 benign cases; on the separate 30-case regression fixture it made 9 false positives out of 12 benign cases. On the separately downloaded, pinned 116-row Deepset held-out test it had TP 58, TN 47, FP 9, FN 2. ONNX conversion changed **none** of those decisions. These data do not establish real-world accuracy or statistical calibration. Full AgentDojo/BIPIA runs, real-weight Windows/macOS/ARM testing and production deployment remain unverified. The scanner is not a replacement for independent authorization, output controls or human review.
