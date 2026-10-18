# CPU inference runtime and artifact provenance

kjnlae 0.3.2 replaces the application's PyTorch/Transformers inference path with ONNX Runtime CPU and the verified tokenizer JSON. PyTorch and Transformers remain optional for fine-tuning, historical comparison and maintainer research. The detector is still **the same fine-tuned English DistilBERT checkpoint**, not a new or fallback classifier. Authorization and output-release checks are independent of either inference runtime.

## Reproducible derivation

The pinned [original public checkpoint](https://huggingface.co/namelessweakling/kjnlae-distilbert-v0.2) is revision `d6f5f455a4bc9b2c4587fc7f3011385a871e3653` with manifest SHA-256 `54e6df56616f4533e1c6a9624f3372ad14bc4d85f5ae97b45c1b3b515a83de9b`. It contains 462 fine-tuned steps, two labels (`NON_INJECTION`, `INJECTION`) and threshold `0.025134501978754997`. The model remains experimental and is not re-trained by this conversion.

An offline PyTorch 2.6 export generated an opset-17 ONNX graph with dynamic batch and sequence axes, `eval()` mode and constant folding disabled. The converter pins ONNX 1.23.2 because its serialization is part of the verified output identity. The source-controlled graph template has **no tensor bytes**. Its SHA-256 is `78e39b995911d8b3fbf66e0e76ee97e6271e17384b7e80ee994946c75bf06fce` (136,246 bytes). `kjnlae model download` fetches the original pinned files only when explicitly invoked, verifies their manifest and per-file digests, fills the graph's 104 named tensors from verified safetensors, and requires the resulting graph SHA-256 to equal `d95dd1850d338f3687f13902869b18e8b6e37f6b23a2dc5845f76133d9dd03a1`. It writes a **separate** derived manifest with SHA-256 `6b69bd6a790119d4c53fe2df02447114eebcdadddec18d788bf1cf6825ecfa1c` and atomically renames the verified output. The staging directory, including original downloaded weights, is removed; an existing installed directory is never overwritten. The public original checkpoint itself is unchanged.

ONNX Runtime opens only the verified local `model.onnx`; runtime never fetches models or imports torch/transformers. The worker uses a hard deadline, bounded batches/windows, verified source offsets and complete-coverage checks. If loading, verification or inference fails, the application returns an explicit `INCOMPLETE` result and retains its independent authorization policy. The graph has not been quantized: an INT8 representation would need its own separately evaluated identity and calibration.

## Measured Linux x86-64 results

Measured on 17 October 2026 in the current cloud environment, with 5 visible CPUs, ~33 GiB RAM and Python 3.12/3.14. Sizes below are **bytes**, not guessed installation figures.

| Quantity | Existing v0.3.1 resolution | New CPU default |
|---|---:|---:|
| Clean pip wheel download resolution, Python 3.12 | 3,053,628,057 | 63,637,670 |
| NVIDIA/CUDA/Triton download share | 2,445,487,866 | 0 |
| Actual default wheel and dependency files after clean pip install, Python 3.14 (excluding pip itself) | Not measured: old CUDA stack was deliberately not installed | 220,269,282 |
| Original model download | 267,832,560 | 267,832,560 |
| Installed derived model files | Not applicable | 268,902,642 |
| Peak temporary files during actual model download/conversion | Not measured | 537,682,357 |
| Hugging Face cache after installer completed | Not measured | 0 |
| Peak main-process RSS during download/conversion | Not measured | 915,599,360 |
| Peak parent-and-worker RSS during 31 actual scans | Not measured | 643,817,472 |
| Single-scan cold start (Python 3.14, model already installed) | Not measured in same harness | 1.345 s |
| 30-scan warm mean, same text, Python 3.14 | Not measured in same harness | 11.07 ms |

The 0.3.1 figure comes from a clean `pip install --dry-run --report` of the repository's 0.3.1 metadata and HEAD `Content-Length` of all resolved wheel URLs. It is a **resolved download total**, not a completed installation or a measured peak. The new figure was measured the same way. A clean `pip install` of the locally built 0.3.2 wheel produced 230,551,558 bytes in `site-packages`, including 10,282,276 bytes for pip itself; kjnlae and its resolved dependencies accounted for 220,269,282 bytes. A separate uv installation without pip/compiled bytecode measured 188,982,828 bytes and is not used as the pip comparison. Interpreter, virtual-environment scaffolding and pip cache are outside these counts. The new download flow was run with an empty Hugging Face home, and its 537,682,357-byte peak sampled the temporary installation directories during the operation. It requires at least 600 MiB free before starting; free-space checks are a minimum, not a filesystem quota guarantee.

## Parity and limitations

A separate PyTorch 2.6 CPU run and the new ONNX worker evaluated the same 80 frozen examples: the 50-case independent set and 30-case original regression set. Every view, token window and source span was compared. The maximum absolute **per-window** model-score difference was `8.94e-7`; there were **zero threshold decision flips**. On the 50-case set, both backends had TP 15, TN 25, FP 10, FN 0 (50 windows). On the 30-case set, both had TP 17, TN 3, FP 9, FN 1 (34 windows). These are small, original project fixtures, not external benchmark scores. The 30-case benign false-positive rate is **75%**. ONNX did not improve the model's false positives. The machine-readable [50-case](reports/onnx-parity-independent.json) and [30-case](reports/onnx-parity-fixtures.json) reports contain the frozen input hashes and full confusion matrices.

The independently held-out [Deepset prompt-injections test parquet](https://huggingface.co/datasets/deepset/prompt-injections) was downloaded locally from revision `4f61ecb038e9c3fb77e21034b22511b523772cdd` and verified against SHA-256 `39ac797cabc157eeed58435a08593b2952bb6cb16fc394a2d383f447cc7b246e`. All **116 rows and 121 windows** were evaluated by both backends at the unchanged threshold, with matching view names and source spans, **zero decision flips**, and maximum absolute per-window score difference `1.282e-6`. Both produced TP 58, TN 47, FP 9, FN 2: precision `0.8657`, recall `0.9667`, F1 `0.9134`, FPR `0.1607`, FNR `0.0333`. The [machine-readable report](reports/onnx-parity-deepset.json) includes the verified source hash. The source parquet and texts were not committed. The dataset has conflicting top-level/nested license metadata; see [provenance](model-data.md). The official test is primarily user-message style and cannot establish detection quality for every RAG/agent trust context.

The comparison used the same source prefix, tokenizer data, token limit (128), overlap (32), window aggregation (maximum score) and threshold. The tokenizer JSON embeds a 128-token truncation default; the ONNX worker explicitly disables that setting before generating bounded, overlapping windows. A real-weight long-input regression test confirms that the last source span reaches the input tail. Without this override, the worker would have silently skipped later tokens while reporting complete inspection. Run `python scripts/compare_runtimes.py --torch ORIGINAL_DIR --onnx ONNX_DIR --hash ONNX_MANIFEST_SHA256 --dataset INPUT.json --output REPORT.json` with the optional `[train]` dependencies to reproduce the per-window comparison; the tool also accepts the pinned Deepset parquet when `pyarrow` is installed. The existing unit and real-worker tests check derived views, coverage, offsets, corruption and timeouts. The model produces window scores and mapped spans, not token-level explanations or calibrated attack-success probabilities.

## Compatibility

"Actual" means installation and real-weight inference executed in this environment. "Wheel" means required platform wheels were visible on PyPI; it is not a runtime test. The [hosted eight-job main-branch CI run](https://github.com/namelessweakl1ng/kjnlae/actions/runs/39092350339) passed, including Windows/macOS no-weight tests; those jobs did not download the model.

| Platform | Python | Evidence / limit |
|---|---|---|
| Linux x86-64 | 3.11, 3.12, 3.13, 3.14 | Actual clean installation and real ONNX `doctor` inference for each version. |
| Linux ARM64 | 3.11–3.14 | Required binary wheels visible; real model not tested. |
| Windows x86-64 | 3.11–3.14 | Required binary wheels visible; real model not tested. |
| macOS Apple Silicon | 3.11–3.14 | ONNX Runtime 1.31 wheels require macOS 14+; real model not tested. |
| macOS Intel 13+ | 3.11–3.13 | ONNX Runtime 1.23.2 is the last checked Intel wheel series; real model not tested. Python 3.14 Intel is unsupported by the checked ONNX Runtime wheels. |

The prior 0.3.1 code's Windows/macOS CI runs cannot establish that this new ONNX backend works there. CI installs the default package and tests no-weight behavior on those operating systems. A maintainer should run real-weight `model download`, `model verify`, `doctor`, API and SDK checks on target hardware before declaring that platform verified.

## Migration from 0.3.1

The public original manifest/hash and its `reviewed-v0.2` directory remain valid for training/research, but the default scanner now requires a **derived ONNX** artifact at `reviewed-v0.2-onnx`. Run `kjnlae model download`, `kjnlae model verify`, then `kjnlae doctor`. Do not point `KJNLAE_MODEL_DIR` at the original safetensors directory or reuse the old manifest hash: that produces an explicit incomplete/corrupted result. The CLI `model download --repo`, `--revision` and `--hash` overrides have been removed to keep default conversion limited to the reviewed source identity. Custom deployment still accepts `KJNLAE_MODEL_DIR` plus `KJNLAE_MODEL_HASH` for the **verified derived artifact**. Install `[api]` for `serve` and `[train]` only for maintainer training/evaluation.
