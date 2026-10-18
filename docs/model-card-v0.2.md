---
language:
  - en
library_name: transformers
pipeline_tag: text-classification
base_model: distilbert/distilbert-base-uncased
datasets:
  - deepset/prompt-injections
license: apache-2.0
inference: false
tags:
  - prompt-injection
  - distilbert
  - experimental
  - offline-inference
---

# kjnlae DistilBERT v0.2 — Experimental Prompt-Injection Classifier

> **Experimental research artifact. NOT production-ready security software.** This model can miss malicious instructions or flag benign text. Never rely on it as the sole safeguard for tools, resources, secrets or regulated systems. Model scores are NOT calibrated probabilities of attack success.

Fine-tuned locally from Apache-2.0 licensed [DistilBERT base uncased](https://huggingface.co/distilbert/distilbert-base-uncased), pinned revision `12040accade4e8a0f71eabdb258fecc2e7e948be`.

The weights implement the sole prompt-injection detector in [kjnlae](https://github.com/namelessweakl1ng/kjnlae), an offline-first Python security gateway with *separate* application-controlled authorization and output-release checks.

**Labels:** `NON_INJECTION` (0) and `INJECTION` (1). English only.

**Verified model manifest SHA-256:** `54e6df56616f4533e1c6a9624f3372ad14bc4d85f5ae97b45c1b3b515a83de9b`.

## Intended use and limitations

Experimental local scanning of untrusted messages, email, webpages, retrieval chunks and tool responses. Pair the classifier with host-verified principal, tenant, grants, tool allowlists, human approvals, resource versions and output release controls. A negative scan never grants action permission. Not validated for production, healthcare, regulated records, or deployment against real autonomous attacks.

## Training provenance

The model adapts the pretrained English DistilBERT encoder and a newly trained two-class classifier head. The final training set had **924 rows (639 benign, 285 injection)**. Separate partitions had 12 validation, 12 calibration and 116 Deepset held-out rows. Sources:

- Original fictional kjnlae training cases and hard benign examples ([provenance](https://github.com/namelessweakl1ng/kjnlae/blob/main/docs/model-data.md)).
- [Microsoft BIPIA](https://github.com/microsoft/BIPIA) active attack prompts, pinned revision `a004b69ec0dd446e0afd461d98cb5e96e120a5d0` (retain LICENSE and NOTICE).
- [Deepset prompt-injections](https://huggingface.co/datasets/deepset/prompt-injections), pinned revision `4f61ecb038e9c3fb77e21034b22511b523772cdd`, plus TRAIN-only source-balanced benign variants. The dataset's top-level metadata reports Apache-2.0 but nested metadata reports CC BY 4.0; see source notices and [the license/provenance discussion](https://github.com/namelessweakl1ng/kjnlae/blob/main/docs/model-data.md).

No raw Deepset or BIPIA examples are included in this model repository.

Training used four CPU cores, batch size 2, 128 tokens, AdamW learning rate 2e-5, seed 42, and two epochs (924 total optimizer steps), taking 351.13 seconds. Validation selected **epoch 1** as the best checkpoint, so the distributed weights represent **462 optimization steps**, not the final epoch.

The gateway's calibration threshold is **0.025134501978754997**, chosen using only 12 calibration rows. This very low value is unstable and likely contributes to false positives. A standard Hugging Face text-classification pipeline does **not** implement kjnlae's text preprocessing, complete-window coverage, calibration threshold or authorization security boundaries, and should not be treated as an equivalent prompt-injection defense.

## Measured evaluation of the reviewed weights

| Evaluation set | TP | TN | FP | FN | Precision | Recall | F1 | Benign FPR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Independent original 50 cases | 15 | 25 | 10 | 0 | .600 | 1.000 | .750 | **28.6%** |
| Original regression 30 cases | 17 | 3 | 9 | 1 | .654 | .944 | .773 | **75.0%** |
| Official Deepset 116 cases | 58 | 47 | 9 | 2 | .866 | .967 | .913 | **16.1%** |

The sample sizes are small and evaluation distributions differ. The earlier model achieved 0% false positives on the Deepset split, so this follow-up was a regression there even though the independent 50-case fixture improved. The current model frequently overflags code and educational quotations. These are **not general deployment accuracy estimates**.

The separately controlled gateway completed 2/2 authorized tasks and blocked 4/4 unauthorized actions in a six-case **scripted synthetic sandbox**, including one classifier miss. There was no live LLM. AgentDojo and full external BIPIA benchmarks were not run.

[Full evaluation report](https://github.com/namelessweakl1ng/kjnlae/blob/main/docs/reports/v0.2-followup-evaluation.md) · [Benchmark methodology](https://github.com/namelessweakl1ng/kjnlae/blob/main/docs/benchmarks.md) · [Known limitations](https://github.com/namelessweakl1ng/kjnlae/blob/main/docs/limitations.md).

## Install and run locally

Clone the [kjnlae 0.3.2 source](https://github.com/namelessweakl1ng/kjnlae) and install it as described in its README. PyPI 0.3.0 is still the older runtime until a separate release. Then, from the project root:

```bash
python -m pip install '.[api]'
kjnlae model download
kjnlae model verify
kjnlae doctor
kjnlae serve
```

The downloader verifies this original checkpoint's pinned manifest and files, derives a separately hashed ONNX CPU artifact, and installs it only after verification. The normal scanning path makes **no network requests**. The destination must not exist before download. The original safetensors checkpoint remains on Hugging Face for training and research; see [ONNX provenance](onnx-runtime.md).

## License and attribution

**Published model weights declare Apache-2.0**, consistent with the base encoder. The kjnlae application code is separately MIT licensed. Distribution of these weights does not override any obligations from the Microsoft BIPIA or Deepset training sources. Refer to their licenses, notices, and the linked provenance report; the Deepset metadata conflict warrants extra review before downstream redistribution or commercial use.

**Published model:** [namelessweakling/kjnlae-distilbert-v0.2](https://huggingface.co/namelessweakling/kjnlae-distilbert-v0.2). A separate Fedora public-download smoke test verified the entire published artifact against the original manifest SHA-256; this does not establish production suitability.
